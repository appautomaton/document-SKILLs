#!/usr/bin/env python3
"""
Library for working with Word documents: comments, tracked changes, and editing.

Usage (with the docx skill directory on sys.path):
    from scripts.document import Document

    # Initialize
    doc = Document('workspace/unpacked')
    doc = Document('workspace/unpacked', author="John Doe", initials="JD")

    # Tracked replacement, found even when the text spans several runs
    doc["word/document.xml"].tracked_replace("30 days", "45 days")

    # Find nodes
    node = doc["word/document.xml"].get_node(tag="w:del", attrs={"w:id": "1"})
    node = doc["word/document.xml"].get_node(tag="w:p", line_number=10)

    # Add comments
    doc.add_comment(start=node, end=node, text="Comment text")
    doc.reply_to_comment(parent_comment_id=0, text="Reply text")

    # Suggest tracked changes
    doc["word/document.xml"].suggest_deletion(node)  # Delete content
    doc["word/document.xml"].revert_insertion(ins_node)  # Reject insertion
    doc["word/document.xml"].revert_deletion(del_node)  # Reject deletion

    # Resolve every tracked change, as Word's Accept All / Reject All
    doc.accept_all_changes()
    doc.reject_all_changes()

    # Save
    doc.save()
"""

import difflib
import html
import random
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from defusedxml import minidom
from ooxml.scripts.pack import pack_document
from ooxml.scripts.validation.docx import DOCXSchemaValidator
from ooxml.scripts.validation.redlining import RedliningValidator

from .utilities import XMLEditor

# Path to template files
TEMPLATE_DIR = Path(__file__).parent / "templates"

MC_NAMESPACE = "http://schemas.openxmlformats.org/markup-compatibility/2006"

# Prefixes the library may write, declared on demand in whichever part needs them.
KNOWN_NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": MC_NAMESPACE,
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}

# Extensions newer than the base standard. Consumers that predate one must be
# told they may skip it, or they reject the file as corrupt.
IGNORABLE_PREFIXES = {"w14", "w15", "w16", "w16cex", "w16cid", "w16du", "wp14"}

# Run children that carry no visible content and never break a text match.
_INVISIBLE_RUN_CHILDREN = {"w:rPr", "w:lastRenderedPageBreak"}

# CJK ideographs, kana and hangul are compared one character at a time, other
# text word by word, so a diff marks "30" in "期限为30天" rather than the whole run.
_DIFF_TOKEN = re.compile(
    r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]"
    r"|[^\W぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]+"
    r"|\s+|."
)


class DocxXMLEditor(XMLEditor):
    """XMLEditor that automatically applies RSID, author, and date to new elements.

    Automatically adds attributes to elements that support them when inserting new content:
    - w:rsidR, w:rsidRDefault, w:rsidP (for w:p and w:r elements)
    - w:author and w:date (for w:ins, w:del, w:comment elements)
    - w:id (for w:ins and w:del elements)

    Attributes:
        dom (defusedxml.minidom.Document): The DOM document for direct manipulation
    """

    def __init__(
        self, xml_path, rsid: str, author: str = "Claude", initials: str = "C"
    ):
        """Initialize with required RSID and optional author.

        Args:
            xml_path: Path to XML file to edit
            rsid: RSID to automatically apply to new elements
            author: Author name for tracked changes and comments (default: "Claude")
            initials: Author initials (default: "C")
        """
        super().__init__(xml_path)
        self.rsid = rsid
        self.author = author
        self.initials = initials

    def _get_next_change_id(self):
        """Get the next available change ID by checking all tracked change elements."""
        max_id = -1
        for tag in ("w:ins", "w:del"):
            elements = self.dom.getElementsByTagName(tag)
            for elem in elements:
                change_id = elem.getAttribute("w:id")
                if change_id:
                    try:
                        max_id = max(max_id, int(change_id))
                    except ValueError:
                        pass
        return max_id + 1

    def _ensure_namespace(self, prefix):
        """Declare a known prefix on the root element, marking extensions ignorable."""
        root = self.dom.documentElement
        if not root.hasAttribute(f"xmlns:{prefix}"):  # type: ignore
            root.setAttribute(f"xmlns:{prefix}", KNOWN_NAMESPACES[prefix])  # type: ignore
        if prefix in IGNORABLE_PREFIXES:
            if not root.hasAttribute("xmlns:mc"):  # type: ignore
                root.setAttribute("xmlns:mc", MC_NAMESPACE)  # type: ignore
            ignorable = root.getAttribute("mc:Ignorable").split()  # type: ignore
            if prefix not in ignorable:
                root.setAttribute("mc:Ignorable", " ".join([*ignorable, prefix]))  # type: ignore

    def _parse_fragment(self, xml_content):
        """Parse a fragment, first declaring any known prefix it uses on the root."""
        for prefix in set(re.findall(r"[<\s/]([A-Za-z][\w]*):[A-Za-z]", xml_content)):
            if prefix in KNOWN_NAMESPACES:
                self._ensure_namespace(prefix)
        return super()._parse_fragment(xml_content)

    def _ensure_w16du_namespace(self):
        self._ensure_namespace("w16du")

    def _ensure_w16cex_namespace(self):
        self._ensure_namespace("w16cex")

    def _ensure_w14_namespace(self):
        self._ensure_namespace("w14")

    def _inject_attributes_to_nodes(self, nodes):
        """Inject RSID, author, and date attributes into DOM nodes where applicable.

        Adds attributes to elements that support them:
        - w:r: gets w:rsidR (or w:rsidDel if inside w:del)
        - w:p: gets w:rsidR, w:rsidRDefault, w:rsidP, w14:paraId, w14:textId
        - w:t: gets xml:space="preserve" if text has leading/trailing whitespace
        - w:ins, w:del: get w:id, w:author, w:date, w16du:dateUtc
        - w:comment: gets w:author, w:date, w:initials
        - w16cex:commentExtensible: gets w16cex:dateUtc

        Args:
            nodes: List of DOM nodes to process
        """
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        def is_inside_deletion(elem):
            """Check if element is inside a w:del element."""
            parent = elem.parentNode
            while parent:
                if parent.nodeType == parent.ELEMENT_NODE and parent.tagName == "w:del":
                    return True
                parent = parent.parentNode
            return False

        def add_rsid_to_p(elem):
            if not elem.hasAttribute("w:rsidR"):
                elem.setAttribute("w:rsidR", self.rsid)
            if not elem.hasAttribute("w:rsidRDefault"):
                elem.setAttribute("w:rsidRDefault", self.rsid)
            if not elem.hasAttribute("w:rsidP"):
                elem.setAttribute("w:rsidP", self.rsid)
            # Add w14:paraId and w14:textId if not present
            if not elem.hasAttribute("w14:paraId"):
                self._ensure_w14_namespace()
                elem.setAttribute("w14:paraId", _generate_hex_id())
            if not elem.hasAttribute("w14:textId"):
                self._ensure_w14_namespace()
                elem.setAttribute("w14:textId", _generate_hex_id())

        def add_rsid_to_r(elem):
            # Use w:rsidDel for <w:r> inside <w:del>, otherwise w:rsidR
            if is_inside_deletion(elem):
                if not elem.hasAttribute("w:rsidDel"):
                    elem.setAttribute("w:rsidDel", self.rsid)
            else:
                if not elem.hasAttribute("w:rsidR"):
                    elem.setAttribute("w:rsidR", self.rsid)

        def add_tracked_change_attrs(elem):
            # Auto-assign w:id if not present
            if not elem.hasAttribute("w:id"):
                elem.setAttribute("w:id", str(self._get_next_change_id()))
            if not elem.hasAttribute("w:author"):
                elem.setAttribute("w:author", self.author)
            if not elem.hasAttribute("w:date"):
                elem.setAttribute("w:date", timestamp)
            # Add w16du:dateUtc for tracked changes (same as w:date since we generate UTC timestamps)
            if elem.tagName in ("w:ins", "w:del") and not elem.hasAttribute(
                "w16du:dateUtc"
            ):
                self._ensure_w16du_namespace()
                elem.setAttribute("w16du:dateUtc", timestamp)

        def add_comment_attrs(elem):
            if not elem.hasAttribute("w:author"):
                elem.setAttribute("w:author", self.author)
            if not elem.hasAttribute("w:date"):
                elem.setAttribute("w:date", timestamp)
            if not elem.hasAttribute("w:initials"):
                elem.setAttribute("w:initials", self.initials)

        def add_comment_extensible_date(elem):
            # Add w16cex:dateUtc for comment extensible elements
            if not elem.hasAttribute("w16cex:dateUtc"):
                self._ensure_w16cex_namespace()
                elem.setAttribute("w16cex:dateUtc", timestamp)

        def add_xml_space_to_t(elem):
            # Add xml:space="preserve" to w:t if text has leading/trailing whitespace
            if (
                elem.firstChild
                and elem.firstChild.nodeType == elem.firstChild.TEXT_NODE
            ):
                text = elem.firstChild.data
                if text and (text[0].isspace() or text[-1].isspace()):
                    if not elem.hasAttribute("xml:space"):
                        elem.setAttribute("xml:space", "preserve")

        for node in nodes:
            if node.nodeType != node.ELEMENT_NODE:
                continue

            # Handle the node itself
            if node.tagName == "w:p":
                add_rsid_to_p(node)
            elif node.tagName == "w:r":
                add_rsid_to_r(node)
            elif node.tagName == "w:t":
                add_xml_space_to_t(node)
            elif node.tagName in ("w:ins", "w:del"):
                add_tracked_change_attrs(node)
            elif node.tagName == "w:comment":
                add_comment_attrs(node)
            elif node.tagName == "w16cex:commentExtensible":
                add_comment_extensible_date(node)

            # Process descendants (getElementsByTagName doesn't return the element itself)
            for elem in node.getElementsByTagName("w:p"):
                add_rsid_to_p(elem)
            for elem in node.getElementsByTagName("w:r"):
                add_rsid_to_r(elem)
            for elem in node.getElementsByTagName("w:t"):
                add_xml_space_to_t(elem)
            for tag in ("w:ins", "w:del"):
                for elem in node.getElementsByTagName(tag):
                    add_tracked_change_attrs(elem)
            for elem in node.getElementsByTagName("w:comment"):
                add_comment_attrs(elem)
            for elem in node.getElementsByTagName("w16cex:commentExtensible"):
                add_comment_extensible_date(elem)

    def replace_node(self, elem, new_content):
        """Replace node with automatic attribute injection."""
        nodes = super().replace_node(elem, new_content)
        self._inject_attributes_to_nodes(nodes)
        return nodes

    def insert_after(self, elem, xml_content):
        """Insert after with automatic attribute injection."""
        nodes = super().insert_after(elem, xml_content)
        self._inject_attributes_to_nodes(nodes)
        return nodes

    def insert_before(self, elem, xml_content):
        """Insert before with automatic attribute injection."""
        nodes = super().insert_before(elem, xml_content)
        self._inject_attributes_to_nodes(nodes)
        return nodes

    def append_to(self, elem, xml_content):
        """Append to with automatic attribute injection."""
        nodes = super().append_to(elem, xml_content)
        self._inject_attributes_to_nodes(nodes)
        return nodes

    def revert_insertion(self, elem):
        """Reject an insertion by wrapping its content in a deletion.

        Wraps all runs inside w:ins in w:del, converting w:t to w:delText.
        Can process a single w:ins element or a container element with multiple w:ins.

        Args:
            elem: Element to process (w:ins, w:p, w:body, etc.)

        Returns:
            list: List containing the processed element(s)

        Raises:
            ValueError: If the element contains no w:ins elements

        Example:
            # Reject a single insertion
            ins = doc["word/document.xml"].get_node(tag="w:ins", attrs={"w:id": "5"})
            doc["word/document.xml"].revert_insertion(ins)

            # Reject all insertions in a paragraph
            para = doc["word/document.xml"].get_node(tag="w:p", line_number=42)
            doc["word/document.xml"].revert_insertion(para)
        """
        # Collect insertions
        ins_elements = []
        if elem.tagName == "w:ins":
            ins_elements.append(elem)
        else:
            ins_elements.extend(elem.getElementsByTagName("w:ins"))

        # Validate that there are insertions to reject
        if not ins_elements:
            raise ValueError(
                f"revert_insertion requires w:ins elements. "
                f"The provided element <{elem.tagName}> contains no insertions. "
            )

        # Process all insertions - wrap all children in w:del
        for ins_elem in ins_elements:
            runs = list(ins_elem.getElementsByTagName("w:r"))
            if not runs:
                continue

            # Create deletion wrapper
            del_wrapper = self.dom.createElement("w:del")

            # Process each run
            for run in runs:
                # Convert w:t → w:delText and w:rsidR → w:rsidDel
                if run.hasAttribute("w:rsidR"):
                    run.setAttribute("w:rsidDel", run.getAttribute("w:rsidR"))
                    run.removeAttribute("w:rsidR")
                elif not run.hasAttribute("w:rsidDel"):
                    run.setAttribute("w:rsidDel", self.rsid)

                for t_elem in list(run.getElementsByTagName("w:t")):
                    del_text = self.dom.createElement("w:delText")
                    # Copy ALL child nodes (not just firstChild) to handle entities
                    while t_elem.firstChild:
                        del_text.appendChild(t_elem.firstChild)
                    for i in range(t_elem.attributes.length):
                        attr = t_elem.attributes.item(i)
                        del_text.setAttribute(attr.name, attr.value)
                    t_elem.parentNode.replaceChild(del_text, t_elem)

            # Move all children from ins to del wrapper
            while ins_elem.firstChild:
                del_wrapper.appendChild(ins_elem.firstChild)

            # Add del wrapper back to ins
            ins_elem.appendChild(del_wrapper)

            # Inject attributes to the deletion wrapper
            self._inject_attributes_to_nodes([del_wrapper])

        return [elem]

    def revert_deletion(self, elem):
        """Reject a deletion by re-inserting the deleted content.

        Creates w:ins elements after each w:del, copying deleted content and
        converting w:delText back to w:t.
        Can process a single w:del element or a container element with multiple w:del.

        Args:
            elem: Element to process (w:del, w:p, w:body, etc.)

        Returns:
            list: If elem is w:del, returns [elem, new_ins]. Otherwise returns [elem].

        Raises:
            ValueError: If the element contains no w:del elements

        Example:
            # Reject a single deletion - returns [w:del, w:ins]
            del_elem = doc["word/document.xml"].get_node(tag="w:del", attrs={"w:id": "3"})
            nodes = doc["word/document.xml"].revert_deletion(del_elem)

            # Reject all deletions in a paragraph - returns [para]
            para = doc["word/document.xml"].get_node(tag="w:p", line_number=42)
            nodes = doc["word/document.xml"].revert_deletion(para)
        """
        # Collect deletions FIRST - before we modify the DOM
        del_elements = []
        is_single_del = elem.tagName == "w:del"

        if is_single_del:
            del_elements.append(elem)
        else:
            del_elements.extend(elem.getElementsByTagName("w:del"))

        # Validate that there are deletions to reject
        if not del_elements:
            raise ValueError(
                f"revert_deletion requires w:del elements. "
                f"The provided element <{elem.tagName}> contains no deletions. "
            )

        # Track created insertion (only relevant if elem is a single w:del)
        created_insertion = None

        # Process all deletions - create insertions that copy the deleted content
        for del_elem in del_elements:
            # Clone the deleted runs and convert them to insertions
            runs = list(del_elem.getElementsByTagName("w:r"))
            if not runs:
                continue

            # Create insertion wrapper
            ins_elem = self.dom.createElement("w:ins")

            for run in runs:
                # Clone the run
                new_run = run.cloneNode(True)

                # Convert w:delText → w:t
                for del_text in list(new_run.getElementsByTagName("w:delText")):
                    t_elem = self.dom.createElement("w:t")
                    # Copy ALL child nodes (not just firstChild) to handle entities
                    while del_text.firstChild:
                        t_elem.appendChild(del_text.firstChild)
                    for i in range(del_text.attributes.length):
                        attr = del_text.attributes.item(i)
                        t_elem.setAttribute(attr.name, attr.value)
                    del_text.parentNode.replaceChild(t_elem, del_text)

                # Update run attributes: w:rsidDel → w:rsidR
                if new_run.hasAttribute("w:rsidDel"):
                    new_run.setAttribute("w:rsidR", new_run.getAttribute("w:rsidDel"))
                    new_run.removeAttribute("w:rsidDel")
                elif not new_run.hasAttribute("w:rsidR"):
                    new_run.setAttribute("w:rsidR", self.rsid)

                ins_elem.appendChild(new_run)

            # Insert the new insertion after the deletion
            nodes = self.insert_after(del_elem, ins_elem.toxml())

            # If processing a single w:del, track the created insertion
            if is_single_del and nodes:
                created_insertion = nodes[0]

        # Return based on input type
        if is_single_del and created_insertion:
            return [elem, created_insertion]
        else:
            return [elem]

    @staticmethod
    def suggest_paragraph(xml_content: str) -> str:
        """Transform paragraph XML to add tracked change wrapping for insertion.

        Wraps runs in <w:ins> and adds <w:ins/> to w:rPr in w:pPr for numbered lists.

        Args:
            xml_content: XML string containing a <w:p> element

        Returns:
            str: Transformed XML with tracked change wrapping
        """
        declarations = " ".join(f'xmlns:{p}="{uri}"' for p, uri in KNOWN_NAMESPACES.items())
        wrapper = f"<root {declarations}>{xml_content}</root>"
        doc = minidom.parseString(wrapper)
        para = doc.getElementsByTagName("w:p")[0]

        # Ensure w:pPr exists
        pPr_list = para.getElementsByTagName("w:pPr")
        if not pPr_list:
            pPr = doc.createElement("w:pPr")
            para.insertBefore(
                pPr, para.firstChild
            ) if para.firstChild else para.appendChild(pPr)
        else:
            pPr = pPr_list[0]

        # Ensure w:rPr exists in w:pPr
        rPr_list = pPr.getElementsByTagName("w:rPr")
        if not rPr_list:
            rPr = doc.createElement("w:rPr")
            pPr.appendChild(rPr)
        else:
            rPr = rPr_list[0]

        # Add <w:ins/> to w:rPr
        ins_marker = doc.createElement("w:ins")
        rPr.insertBefore(
            ins_marker, rPr.firstChild
        ) if rPr.firstChild else rPr.appendChild(ins_marker)

        # Wrap all non-pPr children in <w:ins>
        ins_wrapper = doc.createElement("w:ins")
        for child in [c for c in para.childNodes if c.nodeName != "w:pPr"]:
            para.removeChild(child)
            ins_wrapper.appendChild(child)
        para.appendChild(ins_wrapper)

        return para.toxml()

    def suggest_deletion(self, elem):
        """Mark a w:r or w:p element as deleted with tracked changes (in-place DOM manipulation).

        For w:r: wraps in <w:del>, converts <w:t> to <w:delText>, preserves w:rPr
        For w:p: wraps content in <w:del>, converts <w:t> to <w:delText>, and marks
            the paragraph mark deleted too, so accepting the change removes the
            paragraph instead of leaving it empty. The last paragraph of a body,
            cell or text box keeps its mark, as in Word.

        Args:
            elem: A w:r or w:p DOM element without existing tracked changes

        Returns:
            Element: The modified element

        Raises:
            ValueError: If element has existing tracked changes or invalid structure
        """
        if elem.nodeName == "w:r":
            # Check for existing w:delText
            if elem.getElementsByTagName("w:delText"):
                raise ValueError("w:r element already contains w:delText")

            # Convert w:t → w:delText
            for t_elem in list(elem.getElementsByTagName("w:t")):
                del_text = self.dom.createElement("w:delText")
                # Copy ALL child nodes (not just firstChild) to handle entities
                while t_elem.firstChild:
                    del_text.appendChild(t_elem.firstChild)
                # Preserve attributes like xml:space
                for i in range(t_elem.attributes.length):
                    attr = t_elem.attributes.item(i)
                    del_text.setAttribute(attr.name, attr.value)
                t_elem.parentNode.replaceChild(del_text, t_elem)

            # Update run attributes: w:rsidR → w:rsidDel
            if elem.hasAttribute("w:rsidR"):
                elem.setAttribute("w:rsidDel", elem.getAttribute("w:rsidR"))
                elem.removeAttribute("w:rsidR")
            elif not elem.hasAttribute("w:rsidDel"):
                elem.setAttribute("w:rsidDel", self.rsid)

            # Wrap in w:del
            del_wrapper = self.dom.createElement("w:del")
            parent = elem.parentNode
            parent.insertBefore(del_wrapper, elem)
            parent.removeChild(elem)
            del_wrapper.appendChild(elem)

            # Inject attributes to the deletion wrapper
            self._inject_attributes_to_nodes([del_wrapper])

            return del_wrapper

        elif elem.nodeName == "w:p":
            # Check for existing tracked changes
            if elem.getElementsByTagName("w:ins") or elem.getElementsByTagName("w:del"):
                raise ValueError("w:p element already contains tracked changes")

            # Mark the paragraph mark deleted, unless nothing follows to merge with
            del_marker = None
            if _next_element(elem) is not None and _next_element(elem).tagName == "w:p":
                del_marker = self.dom.createElement("w:del")
                rPr = self._paragraph_mark_rpr(elem)
                rPr.insertBefore(del_marker, rPr.firstChild)

            # Convert w:t → w:delText in all runs
            for t_elem in list(elem.getElementsByTagName("w:t")):
                del_text = self.dom.createElement("w:delText")
                # Copy ALL child nodes (not just firstChild) to handle entities
                while t_elem.firstChild:
                    del_text.appendChild(t_elem.firstChild)
                # Preserve attributes like xml:space
                for i in range(t_elem.attributes.length):
                    attr = t_elem.attributes.item(i)
                    del_text.setAttribute(attr.name, attr.value)
                t_elem.parentNode.replaceChild(del_text, t_elem)

            # Update run attributes: w:rsidR → w:rsidDel
            for run in elem.getElementsByTagName("w:r"):
                if run.hasAttribute("w:rsidR"):
                    run.setAttribute("w:rsidDel", run.getAttribute("w:rsidR"))
                    run.removeAttribute("w:rsidR")
                elif not run.hasAttribute("w:rsidDel"):
                    run.setAttribute("w:rsidDel", self.rsid)

            # Wrap all non-pPr children in <w:del>
            del_wrapper = self.dom.createElement("w:del")
            for child in [c for c in elem.childNodes if c.nodeName != "w:pPr"]:
                elem.removeChild(child)
                del_wrapper.appendChild(child)
            elem.appendChild(del_wrapper)

            # The marker and the wrapper each need their own id, author and date
            self._inject_attributes_to_nodes([n for n in (del_marker, del_wrapper) if n])

            return elem

        else:
            raise ValueError(f"Element must be w:r or w:p, got {elem.nodeName}")

    def _paragraph_mark_rpr(self, para):
        """Return the paragraph mark's <w:rPr>, creating it (and <w:pPr>) if needed."""
        pPr = _child(para, "w:pPr")
        if pPr is None:
            pPr = self.dom.createElement("w:pPr")
            para.insertBefore(pPr, para.firstChild)
        rPr = _child(pPr, "w:rPr")
        if rPr is None:
            rPr = self.dom.createElement("w:rPr")
            # CT_PPr ends with rPr, sectPr, pPrChange, in that order
            follower = _child(pPr, "w:sectPr") or _child(pPr, "w:pPrChange")
            pPr.insertBefore(rPr, follower)
        return rPr

    # ==================== Tracked replacement ====================

    def tracked_replace(self, old, new, scope=None, replace_all=False):
        """Replace `old` with `new` as tracked changes, marking only what differs.

        Finds `old` in a paragraph's visible text even when Word has split it
        across runs: formatting, proofing marks, or a change of script in CJK
        text all split runs. Unchanged text stays in its original runs with
        their formatting and RSIDs. Deleted text keeps its formatting, and
        inserted text takes the formatting of the text it replaces. Tabs and
        line breaks match "\\t" and "\\n".

        Args:
            old: Text to find. It must lie within one paragraph.
            new: Replacement text; "" deletes.
            scope: Element to search within (a paragraph, table, ...). Defaults
                to the whole part.
            replace_all: Replace every occurrence. Otherwise `old` must occur
                exactly once in scope.

        Returns:
            list: The w:del and w:ins elements created, in document order.

        Raises:
            ValueError: If `old` is not found, is ambiguous, or the change would
                have to split another tracked insertion.
        """
        if not old:
            raise ValueError("old must not be empty")
        root = scope if scope is not None else self.dom.documentElement
        paragraphs = [root] if getattr(root, "tagName", None) == "w:p" else list(
            root.getElementsByTagName("w:p")
        )
        matches = []
        for para in paragraphs:
            text = "".join(seg[2] for seg in self._segments(para))
            start = text.find(old)
            while start != -1:
                matches.append((para, start))
                start = text.find(old, start + len(old))

        if not matches:
            raise ValueError(
                f"Text not found: {old!r}. It must lie within one paragraph and match the "
                "visible text exactly (deleted text is not searched)."
            )
        if len(matches) > 1 and not replace_all:
            contexts = "; ".join(
                repr(self._get_element_text(p)[:60]) for p, _ in matches[:5]
            )
            raise ValueError(
                f"{old!r} occurs {len(matches)} times ({contexts}). Pass scope= to narrow "
                "the search, or replace_all=True."
            )

        created = []
        # Last match first, so earlier offsets stay valid as text becomes deleted text
        for para, start in reversed(matches):
            created[:0] = self._replace_in_paragraph(para, start, old, new)
        return created

    def _segments(self, para):
        """Visible content of `para` as (run, child, text) triples, in order.

        Text comes from w:t; a tab is "\\t" and a break "\\n". Any other content
        (fields, drawings, footnote references) is an object-replacement
        character, so no match can span it. Deleted runs are left out.
        """
        segments = []
        for run in _paragraph_runs(para):
            if _inside(run, ("w:del", "w:moveFrom"), stop=para):
                continue
            for child in run.childNodes:
                if child.nodeType != child.ELEMENT_NODE or child.tagName in _INVISIBLE_RUN_CHILDREN:
                    continue
                if child.tagName == "w:t":
                    text = "".join(n.data for n in child.childNodes if n.nodeType == n.TEXT_NODE)
                elif child.tagName == "w:tab":
                    text = "\t"
                elif child.tagName in ("w:br", "w:cr"):
                    text = "\n"
                else:
                    text = "￼"
                if text:
                    segments.append((run, child, text))
        return segments

    def _replace_in_paragraph(self, para, start, old, new):
        # One content child per run. This and the splits below only move run
        # boundaries; the text and formatting are unchanged if a check fails.
        for run in _paragraph_runs(para):
            self._split_run_children(run)
        try:
            plan = self._plan(para, start, _diff_ops(old, new), new)
        except ValueError:
            # Inside another author's insertion only its edges can take new
            # text, so fall back to replacing the whole match at once
            plan = self._plan(para, start, [("replace", 0, len(old), 0, len(new))], new)

        created = []
        for tag, runs, before, after, text in plan:
            if tag == "equal":
                continue
            deletions = [self._wrap_deleted(group) for group in _sibling_groups(runs)]
            created += deletions
            if text:
                style = runs[0] if runs else before or after
                anchor, where = self._outside_insertion(
                    *((deletions[-1], "after") if deletions else self._insertion_point(before, after))
                )
                ins = self._make_insertion(style, text)
                anchor.parentNode.insertBefore(ins, anchor.nextSibling if where == "after" else anchor)
                created.append(ins)
        self._inject_attributes_to_nodes(created)
        return created

    def _plan(self, para, start, ops, new):
        """Map each edit operation onto runs, and check it can be made, before any change.

        Returns (tag, runs covered, run before, run after, text to insert) per
        operation. Raises ValueError if an insertion would land inside an
        existing tracked insertion.
        """
        for offset in sorted({start + i for _, i1, i2, _, _ in ops for i in (i1, i2)}):
            self._split_at(para, offset)
        spans, pos = [], 0
        for run, child, text in self._segments(para):
            spans.append((pos, pos + len(text), run))
            pos += len(text)
        plan = []
        for tag, i1, i2, j1, j2 in ops:
            a, b = start + i1, start + i2
            runs = [r for s, e, r in spans if s >= a and e <= b]
            before = next((r for s, e, r in reversed(spans) if e <= a), None)
            after = next((r for s, e, r in spans if s >= b), None)
            text = new[j1:j2]
            if tag != "equal" and text:
                # A deletion wrapper takes the place of its runs, so the last run stands in for it
                self._outside_insertion(*((runs[-1], "after") if runs else self._insertion_point(before, after)))
            plan.append((tag, runs, before, after, text))
        return plan

    @staticmethod
    def _insertion_point(before, after):
        return (before, "after") if before is not None else (after, "before")

    def _split_run_children(self, run):
        """Split a run holding several content children into one run per child."""
        rPr = _child(run, "w:rPr")
        content = [
            c for c in run.childNodes
            if c.nodeType == c.ELEMENT_NODE and c.tagName != "w:rPr"
        ]
        if len(content) <= 1:
            return
        for child in content:
            piece = run.cloneNode(False)
            if rPr is not None:
                piece.appendChild(rPr.cloneNode(True))
            piece.appendChild(child)  # moves it out of the original run
            run.parentNode.insertBefore(piece, run)
        run.parentNode.removeChild(run)

    def _split_at(self, para, offset):
        """Split the text run that straddles `offset` so a run boundary falls there."""
        pos = 0
        for run, child, text in self._segments(para):
            if pos < offset < pos + len(text):
                if child.tagName != "w:t":
                    raise ValueError("Cannot split inside a tab or break")
                right = run.cloneNode(True)
                k = offset - pos
                _set_text(child, text[:k])
                _set_text(_child(right, "w:t"), text[k:])
                run.parentNode.insertBefore(right, run.nextSibling)
                return
            pos += len(text)

    def _wrap_deleted(self, runs):
        """Wrap consecutive sibling runs in one <w:del>, turning their text into deleted text."""
        wrapper = self.dom.createElement("w:del")
        runs[0].parentNode.insertBefore(wrapper, runs[0])
        for run in runs:
            for t in list(run.getElementsByTagName("w:t")):
                _rename(self.dom, t, "w:delText")
            for t in list(run.getElementsByTagName("w:instrText")):
                _rename(self.dom, t, "w:delInstrText")
            if run.hasAttribute("w:rsidR"):
                run.setAttribute("w:rsidDel", run.getAttribute("w:rsidR"))
                run.removeAttribute("w:rsidR")
            wrapper.appendChild(run)
        return wrapper

    def _make_insertion(self, style_run, text):
        """A <w:ins> holding `text` in a run formatted like `style_run`."""
        rPr = _child(style_run, "w:rPr") if style_run is not None else None
        rpr_xml = rPr.toxml() if rPr is not None else ""
        parts = []
        for piece in re.split(r"(\t|\n)", text):
            if piece == "\t":
                parts.append("<w:tab/>")
            elif piece == "\n":
                parts.append("<w:br/>")
            elif piece:
                parts.append(f'<w:t xml:space="preserve">{html.escape(piece, quote=False)}</w:t>')
        return self._parse_fragment(f"<w:ins><w:r>{rpr_xml}{''.join(parts)}</w:r></w:ins>")[0]

    def _outside_insertion(self, anchor, where):
        """Move an insertion point out of an existing <w:ins>, which cannot nest another.

        Only the edges of that insertion are reachable without splitting it,
        which would change its identity.
        """
        node = anchor
        while node.parentNode is not None and node.parentNode.nodeType == node.ELEMENT_NODE:
            parent = node.parentNode
            if parent.tagName == "w:p":
                break
            if parent.tagName == "w:ins":
                siblings = [c for c in parent.childNodes if c.nodeType == c.ELEMENT_NODE]
                at_edge = siblings[-1] is node if where == "after" else siblings[0] is node
                if not at_edge:
                    raise ValueError(
                        f"The change falls inside {parent.getAttribute('w:author') or 'another'}'s "
                        "tracked insertion. Replace the whole insertion, or use revert_insertion()."
                    )
                anchor = parent
            node = parent
        return anchor, where

    # ==================== Resolving tracked changes ====================

    _PROPERTY_CHANGES = (
        "w:rPrChange", "w:pPrChange", "w:sectPrChange", "w:tblPrChange", "w:trPrChange",
        "w:tcPrChange", "w:tblGridChange", "w:tblPrExChange", "w:numberingChange",
    )

    def accept_all_changes(self):
        """Accept every tracked change in this part. See Document.accept_all_changes()."""
        self._resolve_changes(accept=True)

    def reject_all_changes(self):
        """Reject every tracked change in this part. See Document.reject_all_changes()."""
        self._resolve_changes(accept=False)

    def _resolve_changes(self, accept):
        keep, drop = ("w:ins", "w:moveTo"), ("w:del", "w:moveFrom")
        if not accept:
            keep, drop = drop, keep
        markers, rows, content = [], [], []
        for tag in (*keep, *drop):
            for elem in self.dom.getElementsByTagName(tag):
                parent = elem.parentNode.tagName
                if parent == "w:rPr":
                    markers.append(elem)
                elif parent == "w:trPr":
                    rows.append(elem)
                else:
                    content.append(elem)

        # Removed content first, so a deletion nested in an insertion goes with it
        for elem in content:
            if elem.tagName in drop and elem.parentNode is not None:
                elem.parentNode.removeChild(elem)
        for elem in content:
            if elem.tagName in keep and elem.parentNode is not None:
                if not accept:  # rejecting a deletion turns its text back into text
                    for t in list(elem.getElementsByTagName("w:delText")):
                        _rename(self.dom, t, "w:t")
                    for t in list(elem.getElementsByTagName("w:delInstrText")):
                        _rename(self.dom, t, "w:instrText")
                    for run in elem.getElementsByTagName("w:r"):
                        if run.hasAttribute("w:rsidDel"):
                            run.removeAttribute("w:rsidDel")
                while elem.firstChild:
                    elem.parentNode.insertBefore(elem.firstChild, elem)
                elem.parentNode.removeChild(elem)

        for marker in rows:
            row = marker.parentNode.parentNode
            if marker.tagName in drop and row.parentNode is not None:
                row.parentNode.removeChild(row)
            elif marker.parentNode is not None:
                marker.parentNode.removeChild(marker)

        # A removed paragraph mark joins its paragraph to the next one, whose
        # mark (and so paragraph formatting) survives
        for marker in markers:
            rPr = marker.parentNode
            pPr = rPr.parentNode
            rPr.removeChild(marker)
            para = pPr.parentNode if pPr.tagName == "w:pPr" else None
            # Drop properties the marker leaves empty
            for props in (rPr, pPr):
                if props.tagName in ("w:rPr", "w:pPr") and not any(
                    c.nodeType == c.ELEMENT_NODE for c in props.childNodes
                ) and props.parentNode is not None:
                    props.parentNode.removeChild(props)
            if marker.tagName not in drop or para is None or para.tagName != "w:p":
                continue
            following = _next_element(para)
            if following is None or following.tagName != "w:p" or _child(pPr, "w:sectPr"):
                continue
            anchor = _child(following, "w:pPr")
            anchor = anchor.nextSibling if anchor is not None else following.firstChild
            for child in [c for c in para.childNodes if c.nodeName != "w:pPr"]:
                following.insertBefore(child, anchor)
            para.parentNode.removeChild(para)

        for tag in self._PROPERTY_CHANGES:
            for change in list(self.dom.getElementsByTagName(tag)):
                parent = change.parentNode
                if not accept:
                    self._restore_properties(parent, change)
                parent.removeChild(change)

        for tag in ("w:moveFromRangeStart", "w:moveFromRangeEnd",
                    "w:moveToRangeStart", "w:moveToRangeEnd"):
            for elem in list(self.dom.getElementsByTagName(tag)):
                elem.parentNode.removeChild(elem)

    def _restore_properties(self, props, change):
        """Put back the properties a *Change element recorded as the originals."""
        previous = next((c for c in change.childNodes if c.nodeType == c.ELEMENT_NODE), None)
        kept = {change.tagName}
        if props.tagName == "w:pPr":  # the record covers neither the mark's rPr nor sectPr
            kept |= {"w:rPr", "w:sectPr"}
        elif props.tagName == "w:rPr":  # paragraph-mark revision markers stay
            kept |= {"w:ins", "w:del", "w:moveFrom", "w:moveTo"}
        for child in list(props.childNodes):
            if child.nodeType != child.ELEMENT_NODE or child.tagName not in kept:
                props.removeChild(child)
        if previous is None:
            return
        anchor = change
        if props.tagName == "w:pPr":
            anchor = _child(props, "w:rPr") or _child(props, "w:sectPr") or change
        for child in list(previous.childNodes):
            props.insertBefore(child, anchor)


def _child(elem, tag):
    """First direct child element of `elem` with `tag`, or None."""
    for c in elem.childNodes:
        if c.nodeType == c.ELEMENT_NODE and c.tagName == tag:
            return c
    return None


def _next_element(elem):
    node = elem.nextSibling
    while node is not None and node.nodeType != node.ELEMENT_NODE:
        node = node.nextSibling
    return node


def _inside(elem, tags, stop):
    """Whether an ancestor of `elem` below `stop` has one of `tags`."""
    node = elem.parentNode
    while node is not None and node is not stop:
        if node.nodeType == node.ELEMENT_NODE and node.tagName in tags:
            return True
        node = node.parentNode
    return False


def _paragraph_runs(para):
    """Runs whose nearest enclosing paragraph is `para`, in document order."""
    runs = []

    def walk(node):
        for c in node.childNodes:
            if c.nodeType != c.ELEMENT_NODE or c.tagName in ("w:p", "w:pPr"):
                continue
            if c.tagName == "w:r":
                runs.append(c)
            else:
                walk(c)

    walk(para)
    return runs


def _sibling_groups(runs):
    """Split runs into groups of adjacent element siblings."""
    groups = []
    for run in runs:
        if groups and _next_element(groups[-1][-1]) is run:
            groups[-1].append(run)
        else:
            groups.append([run])
    return groups


def _set_text(t_elem, text):
    while t_elem.firstChild:
        t_elem.removeChild(t_elem.firstChild)
    t_elem.appendChild(t_elem.ownerDocument.createTextNode(text))
    if text[:1].isspace() or text[-1:].isspace():
        t_elem.setAttribute("xml:space", "preserve")


def _rename(dom, elem, tag):
    """Replace `elem` with an element named `tag` holding its children and attributes."""
    renamed = dom.createElement(tag)
    while elem.firstChild:
        renamed.appendChild(elem.firstChild)
    for i in range(elem.attributes.length):
        attr = elem.attributes.item(i)
        renamed.setAttribute(attr.name, attr.value)
    elem.parentNode.replaceChild(renamed, elem)
    return renamed


def _diff_ops(old, new):
    """Edit operations turning `old` into `new`, as character-offset opcodes.

    Words are compared whole and CJK characters singly. A whitespace-only
    match between two changes is folded into them, so "red car" -> "blue truck"
    reads as one replacement rather than two.
    """
    a, b = _DIFF_TOKEN.findall(old), _DIFF_TOKEN.findall(new)
    pos_a, pos_b = [0], [0]
    for tok in a:
        pos_a.append(pos_a[-1] + len(tok))
    for tok in b:
        pos_b.append(pos_b[-1] + len(tok))
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        ops.append([tag, pos_a[i1], pos_a[i2], pos_b[j1], pos_b[j2]])
    merged = []
    for k, op in enumerate(ops):
        folds = (
            op[0] == "equal"
            and not old[op[1]:op[2]].strip()
            and 0 < k < len(ops) - 1
            and ops[k + 1][0] != "equal"
        )
        if merged and merged[-1][0] != "equal" and (folds or op[0] != "equal"):
            merged[-1] = ["replace", merged[-1][1], op[2], merged[-1][3], op[4]]
        else:
            merged.append(op)
    return [tuple(op) for op in merged]


def _generate_hex_id() -> str:
    """Generate random 8-character hex ID for para/durable IDs.

    Values are constrained to be less than 0x7FFFFFFF per OOXML spec:
    - paraId must be < 0x80000000
    - durableId must be < 0x7FFFFFFF
    We use the stricter constraint (0x7FFFFFFF) for both.
    """
    return f"{random.randint(1, 0x7FFFFFFE):08X}"


def _generate_rsid() -> str:
    """Generate random 8-character hex RSID."""
    return "".join(random.choices("0123456789ABCDEF", k=8))


# Child element order of CT_Settings per ECMA-376 / ISO-IEC 29500
# (ooxml/schemas/ISO-IEC29500-4_2016/wml.xsd, CT_Settings sequence). Used to
# insert new settings.xml elements at a schema-valid position regardless of
# which optional settings the source document already contains.
_CT_SETTINGS_ORDER = (
    "writeProtection", "view", "zoom", "removePersonalInformation", "removeDateAndTime",
    "doNotDisplayPageBoundaries", "displayBackgroundShape", "printPostScriptOverText",
    "printFractionalCharacterWidth", "printFormsData", "embedTrueTypeFonts", "embedSystemFonts",
    "saveSubsetFonts", "saveFormsData", "mirrorMargins", "alignBordersAndEdges",
    "bordersDoNotSurroundHeader", "bordersDoNotSurroundFooter", "gutterAtTop", "hideSpellingErrors",
    "hideGrammaticalErrors", "activeWritingStyle", "proofState", "formsDesign", "attachedTemplate",
    "linkStyles", "stylePaneFormatFilter", "stylePaneSortMethod", "documentType", "mailMerge",
    "revisionView", "trackRevisions", "doNotTrackMoves", "doNotTrackFormatting", "documentProtection",
    "autoFormatOverride", "styleLockTheme", "styleLockQFSet", "defaultTabStop", "autoHyphenation",
    "consecutiveHyphenLimit", "hyphenationZone", "doNotHyphenateCaps", "showEnvelope", "summaryLength",
    "clickAndTypeStyle", "defaultTableStyle", "evenAndOddHeaders", "bookFoldRevPrinting",
    "bookFoldPrinting", "bookFoldPrintingSheets", "drawingGridHorizontalSpacing",
    "drawingGridVerticalSpacing", "displayHorizontalDrawingGridEvery", "displayVerticalDrawingGridEvery",
    "doNotUseMarginsForDrawingGridOrigin", "drawingGridHorizontalOrigin", "drawingGridVerticalOrigin",
    "doNotShadeFormData", "noPunctuationKerning", "characterSpacingControl", "printTwoOnOne",
    "strictFirstAndLastChars", "noLineBreaksAfter", "noLineBreaksBefore", "savePreviewPicture",
    "doNotValidateAgainstSchema", "saveInvalidXml", "ignoreMixedContent", "alwaysShowPlaceholderText",
    "doNotDemarcateInvalidXml", "saveXmlDataOnly", "useXSLTWhenSaving", "saveThroughXslt",
    "showXMLTags", "alwaysMergeEmptyNamespace", "updateFields", "hdrShapeDefaults", "footnotePr",
    "endnotePr", "compat", "docVars", "rsids", "attachedSchema", "themeFontLang", "clrSchemeMapping",
    "doNotIncludeSubdocsInStats", "doNotAutoCompressPictures", "forceUpgrade", "captions",
    "readModeInkLockDown", "smartTagType", "shapeDefaults", "doNotEmbedSmartTags", "decimalSymbol",
    "listSeparator",
)


def _insert_settings_element(editor, root, local_name, xml):
    """Insert `xml` into <w:settings> at the schema-valid position for `local_name`.

    Inserts before the first existing child that must follow `local_name` per
    _CT_SETTINGS_ORDER; if none exists, appends. Unknown/extension elements are
    skipped when scanning. Caller ensures the element does not already exist.
    """
    try:
        target_idx = _CT_SETTINGS_ORDER.index(local_name)
    except ValueError:
        target_idx = len(_CT_SETTINGS_ORDER)
    for child in root.childNodes:
        if child.nodeType != child.ELEMENT_NODE:
            continue
        child_local = child.tagName.split(":")[-1]
        try:
            child_idx = _CT_SETTINGS_ORDER.index(child_local)
        except ValueError:
            continue
        if child_idx > target_idx:
            editor.insert_before(child, xml)
            return
    editor.append_to(root, xml)


class Document:
    """Manages comments in unpacked Word documents."""

    def __init__(
        self,
        unpacked_dir,
        rsid=None,
        track_revisions=False,
        author="Claude",
        initials="C",
    ):
        """
        Initialize with path to unpacked Word document directory.
        Automatically sets up comment infrastructure (people.xml, RSIDs).

        Args:
            unpacked_dir: Path to unpacked DOCX directory (must contain word/ subdirectory)
            rsid: Optional RSID to use for all comment elements. If not provided, one will be generated.
            track_revisions: If True, enables track revisions in settings.xml (default: False)
            author: Default author name for comments (default: "Claude")
            initials: Default author initials for comments (default: "C")
        """
        self.original_path = Path(unpacked_dir)

        if not self.original_path.exists() or not self.original_path.is_dir():
            raise ValueError(f"Directory not found: {unpacked_dir}")

        # Create temporary directory with subdirectories for unpacked content and baseline
        self.temp_dir = tempfile.mkdtemp(prefix="docx_")
        self.unpacked_path = Path(self.temp_dir) / "unpacked"
        shutil.copytree(self.original_path, self.unpacked_path)

        # Pack original directory into temporary .docx for validation baseline (outside unpacked dir)
        self.original_docx = Path(self.temp_dir) / "original.docx"
        pack_document(self.original_path, self.original_docx, validate=False)

        self.word_path = self.unpacked_path / "word"

        # Generate RSID if not provided
        self.rsid = rsid if rsid else _generate_rsid()
        print(f"Using RSID: {self.rsid}")

        # Set default author and initials
        self.author = author
        self.initials = initials

        # Cache for lazy-loaded editors
        self._editors = {}

        # Comment file paths
        self.comments_path = self.word_path / "comments.xml"
        self.comments_extended_path = self.word_path / "commentsExtended.xml"
        self.comments_ids_path = self.word_path / "commentsIds.xml"
        self.comments_extensible_path = self.word_path / "commentsExtensible.xml"

        # Load existing comments and determine next ID (before setup modifies files)
        self.existing_comments = self._load_existing_comments()
        self.next_comment_id = self._get_next_comment_id()

        # Convenient access to document.xml editor (semi-private)
        self._document = self["word/document.xml"]

        # Setup tracked changes infrastructure
        self._setup_tracking(track_revisions=track_revisions)

        # Add author to people.xml
        self._add_author_to_people(author)

    def __getitem__(self, xml_path: str) -> DocxXMLEditor:
        """
        Get or create a DocxXMLEditor for the specified XML file.

        Enables lazy-loaded editors with bracket notation:
            node = doc["word/document.xml"].get_node(tag="w:p", line_number=42)

        Args:
            xml_path: Relative path to XML file (e.g., "word/document.xml", "word/comments.xml")

        Returns:
            DocxXMLEditor instance for the specified file

        Raises:
            ValueError: If the file does not exist

        Example:
            # Get node from document.xml
            node = doc["word/document.xml"].get_node(tag="w:del", attrs={"w:id": "1"})

            # Get node from comments.xml
            comment = doc["word/comments.xml"].get_node(tag="w:comment", attrs={"w:id": "0"})
        """
        if xml_path not in self._editors:
            file_path = self.unpacked_path / xml_path
            if not file_path.exists():
                raise ValueError(f"XML file not found: {xml_path}")
            # Use DocxXMLEditor with RSID, author, and initials for all editors
            self._editors[xml_path] = DocxXMLEditor(
                file_path, rsid=self.rsid, author=self.author, initials=self.initials
            )
        return self._editors[xml_path]

    def add_comment(self, start, end, text: str) -> int:
        """
        Add a comment spanning from one element to another.

        Args:
            start: DOM element for the starting point
            end: DOM element for the ending point
            text: Comment content

        Returns:
            The comment ID that was created

        Example:
            start_node = doc["word/document.xml"].get_node(tag="w:del", attrs={"w:id": "1"})
            end_node = doc["word/document.xml"].get_node(tag="w:ins", attrs={"w:id": "2"})
            doc.add_comment(start=start_node, end=end_node, text="Explanation")
        """
        comment_id = self.next_comment_id
        para_id = _generate_hex_id()
        durable_id = _generate_hex_id()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Add comment ranges to document.xml immediately. A paragraph anchor
        # starts inside the paragraph, after its properties, where every
        # consumer looks for it.
        if start.tagName == "w:p":
            pPr = _child(start, "w:pPr")
            if pPr is not None:
                self._document.insert_after(pPr, self._comment_range_start_xml(comment_id))
            elif start.firstChild is not None:
                self._document.insert_before(start.firstChild, self._comment_range_start_xml(comment_id))
            else:
                self._document.append_to(start, self._comment_range_start_xml(comment_id))
        else:
            self._document.insert_before(start, self._comment_range_start_xml(comment_id))

        # If end node is a paragraph, append comment markup inside it
        # Otherwise insert after it (for run-level anchors)
        if end.tagName == "w:p":
            self._document.append_to(end, self._comment_range_end_xml(comment_id))
        else:
            self._document.insert_after(end, self._comment_range_end_xml(comment_id))

        # Add to comments.xml immediately
        self._add_to_comments_xml(
            comment_id, para_id, text, self.author, self.initials, timestamp
        )

        # Add to commentsExtended.xml immediately
        self._add_to_comments_extended_xml(para_id, parent_para_id=None)

        # Add to commentsIds.xml immediately
        self._add_to_comments_ids_xml(para_id, durable_id)

        # Add to commentsExtensible.xml immediately
        self._add_to_comments_extensible_xml(durable_id)

        # Update existing_comments so replies work
        self.existing_comments[comment_id] = {"para_id": para_id}

        self.next_comment_id += 1
        return comment_id

    def reply_to_comment(
        self,
        parent_comment_id: int,
        text: str,
    ) -> int:
        """
        Add a reply to an existing comment.

        Args:
            parent_comment_id: The w:id of the parent comment to reply to
            text: Reply text

        Returns:
            The comment ID that was created for the reply

        Example:
            doc.reply_to_comment(parent_comment_id=0, text="I agree with this change")
        """
        if parent_comment_id not in self.existing_comments:
            raise ValueError(f"Parent comment with id={parent_comment_id} not found")

        parent_info = self.existing_comments[parent_comment_id]
        comment_id = self.next_comment_id
        para_id = _generate_hex_id()
        durable_id = _generate_hex_id()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Add comment ranges to document.xml immediately
        parent_start_elem = self._document.get_node(
            tag="w:commentRangeStart", attrs={"w:id": str(parent_comment_id)}
        )
        parent_ref_elem = self._document.get_node(
            tag="w:commentReference", attrs={"w:id": str(parent_comment_id)}
        )

        self._document.insert_after(
            parent_start_elem, self._comment_range_start_xml(comment_id)
        )
        parent_ref_run = parent_ref_elem.parentNode
        self._document.insert_after(
            parent_ref_run, f'<w:commentRangeEnd w:id="{comment_id}"/>'
        )
        self._document.insert_after(
            parent_ref_run, self._comment_ref_run_xml(comment_id)
        )

        # Add to comments.xml immediately
        self._add_to_comments_xml(
            comment_id, para_id, text, self.author, self.initials, timestamp
        )

        # Add to commentsExtended.xml immediately (with parent)
        self._add_to_comments_extended_xml(
            para_id, parent_para_id=parent_info["para_id"]
        )

        # Add to commentsIds.xml immediately
        self._add_to_comments_ids_xml(para_id, durable_id)

        # Add to commentsExtensible.xml immediately
        self._add_to_comments_extensible_xml(durable_id)

        # Update existing_comments so replies work
        self.existing_comments[comment_id] = {"para_id": para_id}

        self.next_comment_id += 1
        return comment_id

    def accept_all_changes(self):
        """Accept every tracked change in the document, as Word's Accept All does.

        Covers the body, headers, footers, footnotes, endnotes and comments.
        Call it before making your own edits: edits made earlier must already
        be tracked, and later ones are checked against the accepted document.
        """
        self._resolve_all(accept=True)

    def reject_all_changes(self):
        """Reject every tracked change in the document, as Word's Reject All does.

        Same scope and ordering rules as accept_all_changes().
        """
        self._resolve_all(accept=False)

    def __del__(self):
        """Clean up temporary directory on deletion."""
        if hasattr(self, "temp_dir") and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def validate(self, require_tracking=True) -> None:
        """
        Validate the document against the XSD schema and, by default, check
        that every change since loading is a tracked change.

        Raises:
            ValueError: If validation fails.
        """
        schema_validator = DOCXSchemaValidator(
            self.unpacked_path, self.original_docx, verbose=False
        )
        if not schema_validator.validate():
            raise ValueError("Schema validation failed")
        if require_tracking and not RedliningValidator(
            self.unpacked_path, self.original_docx, verbose=False, author=self.author
        ).validate():
            raise ValueError("Redlining validation failed")

    def save(self, destination=None, validate=True, require_tracking=True) -> None:
        """
        Save all modified XML files to disk and copy to destination directory.

        Args:
            destination: Optional path to save to. If None, saves back to original directory.
            validate: If True, validates document before saving (default: True).
            require_tracking: If True (default), every edit must be a tracked
                change. Pass False to edit a document of your own directly; the
                schema is still checked.
        """
        # Only ensure comment relationships and content types if comment files exist
        if self.comments_path.exists():
            self._ensure_comment_relationships()
            self._ensure_comment_content_types()

        # Save all modified XML files in temp directory
        for editor in self._editors.values():
            editor.save()

        # Validate by default
        if validate:
            self.validate(require_tracking=require_tracking)

        # Copy contents from temp directory to destination (or original directory)
        target_path = Path(destination) if destination else self.original_path
        shutil.copytree(self.unpacked_path, target_path, dirs_exist_ok=True)

    # ==================== Private: Initialization ====================

    def _get_next_comment_id(self):
        """Get the next available comment ID."""
        if not self.comments_path.exists():
            return 0

        editor = self["word/comments.xml"]
        max_id = -1
        for comment_elem in editor.dom.getElementsByTagName("w:comment"):
            comment_id = comment_elem.getAttribute("w:id")
            if comment_id:
                try:
                    max_id = max(max_id, int(comment_id))
                except ValueError:
                    pass
        return max_id + 1

    def _load_existing_comments(self):
        """Load existing comments from files to enable replies."""
        if not self.comments_path.exists():
            return {}

        editor = self["word/comments.xml"]
        existing = {}

        for comment_elem in editor.dom.getElementsByTagName("w:comment"):
            comment_id = comment_elem.getAttribute("w:id")
            if not comment_id:
                continue

            # Find para_id from the w:p element within the comment
            para_id = None
            for p_elem in comment_elem.getElementsByTagName("w:p"):
                para_id = p_elem.getAttribute("w14:paraId")
                if para_id:
                    break

            if not para_id:
                continue

            existing[int(comment_id)] = {"para_id": para_id}

        return existing

    # ==================== Private: Setup Methods ====================

    def _setup_tracking(self, track_revisions=False):
        """Set up comment infrastructure in unpacked directory.

        Args:
            track_revisions: If True, enables track revisions in settings.xml
        """
        # Create or update word/people.xml
        people_file = self.word_path / "people.xml"
        self._update_people_xml(people_file)

        # Update XML files
        self._add_content_type_for_people(self.unpacked_path / "[Content_Types].xml")
        self._add_relationship_for_people(
            self.word_path / "_rels" / "document.xml.rels"
        )

        # Always add RSID to settings.xml, optionally enable trackRevisions
        self._update_settings(
            self.word_path / "settings.xml", track_revisions=track_revisions
        )

    def _update_people_xml(self, path):
        """Create people.xml if it doesn't exist."""
        if not path.exists():
            # Copy from template
            shutil.copy(TEMPLATE_DIR / "people.xml", path)

    def _add_content_type_for_people(self, path):
        """Add people.xml content type to [Content_Types].xml if not already present."""
        editor = self["[Content_Types].xml"]

        if self._has_override(editor, "/word/people.xml"):
            return

        # Add Override element
        root = editor.dom.documentElement
        override_xml = '<Override PartName="/word/people.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.people+xml"/>'
        editor.append_to(root, override_xml)

    def _add_relationship_for_people(self, path):
        """Add people.xml relationship to document.xml.rels if not already present."""
        editor = self["word/_rels/document.xml.rels"]

        if self._has_relationship(editor, "people.xml"):
            return

        root = editor.dom.documentElement
        root_tag = root.tagName  # type: ignore
        prefix = root_tag.split(":")[0] + ":" if ":" in root_tag else ""
        next_rid = editor.get_next_rid()

        # Create the relationship entry
        rel_xml = f'<{prefix}Relationship Id="{next_rid}" Type="http://schemas.microsoft.com/office/2011/relationships/people" Target="people.xml"/>'
        editor.append_to(root, rel_xml)

    def _update_settings(self, path, track_revisions=False):
        """Add RSID and optionally enable track revisions in settings.xml.

        Args:
            path: Path to settings.xml
            track_revisions: If True, adds a <w:trackRevisions/> element

        New elements are placed at their schema-valid position via
        _insert_settings_element (CT_Settings child order), so the result
        validates regardless of which optional settings the source file has.
        """
        editor = self["word/settings.xml"]
        root = editor.get_node(tag="w:settings")
        prefix = root.tagName.split(":")[0] if ":" in root.tagName else "w"

        # Conditionally add trackRevisions if requested
        if track_revisions and not editor.dom.getElementsByTagName(
            f"{prefix}:trackRevisions"
        ):
            _insert_settings_element(
                editor, root, "trackRevisions", f"<{prefix}:trackRevisions/>"
            )

        # Ensure an rsids section exists and contains this session's RSID
        rsids_elements = editor.dom.getElementsByTagName(f"{prefix}:rsids")

        if not rsids_elements:
            rsids_xml = f'''<{prefix}:rsids>
  <{prefix}:rsidRoot {prefix}:val="{self.rsid}"/>
  <{prefix}:rsid {prefix}:val="{self.rsid}"/>
</{prefix}:rsids>'''
            _insert_settings_element(editor, root, "rsids", rsids_xml)
        else:
            # Check if this rsid already exists
            rsids_elem = rsids_elements[0]
            rsid_exists = any(
                elem.getAttribute(f"{prefix}:val") == self.rsid
                for elem in rsids_elem.getElementsByTagName(f"{prefix}:rsid")
            )

            if not rsid_exists:
                rsid_xml = f'<{prefix}:rsid {prefix}:val="{self.rsid}"/>'
                editor.append_to(rsids_elem, rsid_xml)

    # ==================== Private: XML File Creation ====================

    def _add_to_comments_xml(
        self, comment_id, para_id, text, author, initials, timestamp
    ):
        """Add a single comment to comments.xml."""
        if not self.comments_path.exists():
            shutil.copy(TEMPLATE_DIR / "comments.xml", self.comments_path)

        editor = self["word/comments.xml"]
        root = editor.get_node(tag="w:comments")

        escaped_text = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        # Note: w:rsidR, w:rsidRDefault, w:rsidP on w:p, w:rsidR on w:r,
        # and w:author, w:date, w:initials on w:comment are automatically added by DocxXMLEditor
        comment_xml = f'''<w:comment w:id="{comment_id}">
  <w:p w14:paraId="{para_id}" w14:textId="77777777">
    <w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:annotationRef/></w:r>
    <w:r><w:rPr><w:color w:val="000000"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr><w:t>{escaped_text}</w:t></w:r>
  </w:p>
</w:comment>'''
        editor.append_to(root, comment_xml)

    def _add_to_comments_extended_xml(self, para_id, parent_para_id):
        """Add a single comment to commentsExtended.xml."""
        if not self.comments_extended_path.exists():
            shutil.copy(
                TEMPLATE_DIR / "commentsExtended.xml", self.comments_extended_path
            )

        editor = self["word/commentsExtended.xml"]
        root = editor.get_node(tag="w15:commentsEx")

        if parent_para_id:
            xml = f'<w15:commentEx w15:paraId="{para_id}" w15:paraIdParent="{parent_para_id}" w15:done="0"/>'
        else:
            xml = f'<w15:commentEx w15:paraId="{para_id}" w15:done="0"/>'
        editor.append_to(root, xml)

    def _add_to_comments_ids_xml(self, para_id, durable_id):
        """Add a single comment to commentsIds.xml."""
        if not self.comments_ids_path.exists():
            shutil.copy(TEMPLATE_DIR / "commentsIds.xml", self.comments_ids_path)

        editor = self["word/commentsIds.xml"]
        root = editor.get_node(tag="w16cid:commentsIds")

        xml = f'<w16cid:commentId w16cid:paraId="{para_id}" w16cid:durableId="{durable_id}"/>'
        editor.append_to(root, xml)

    def _add_to_comments_extensible_xml(self, durable_id):
        """Add a single comment to commentsExtensible.xml."""
        if not self.comments_extensible_path.exists():
            shutil.copy(
                TEMPLATE_DIR / "commentsExtensible.xml", self.comments_extensible_path
            )

        editor = self["word/commentsExtensible.xml"]
        root = editor.get_node(tag="w16cex:commentsExtensible")

        xml = f'<w16cex:commentExtensible w16cex:durableId="{durable_id}"/>'
        editor.append_to(root, xml)

    # ==================== Private: XML Fragments ====================

    def _comment_range_start_xml(self, comment_id):
        """Generate XML for comment range start."""
        return f'<w:commentRangeStart w:id="{comment_id}"/>'

    def _comment_range_end_xml(self, comment_id):
        """Generate XML for comment range end with reference run.

        Note: w:rsidR is automatically added by DocxXMLEditor.
        """
        return f'''<w:commentRangeEnd w:id="{comment_id}"/>
<w:r>
  <w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>
  <w:commentReference w:id="{comment_id}"/>
</w:r>'''

    def _comment_ref_run_xml(self, comment_id):
        """Generate XML for comment reference run.

        Note: w:rsidR is automatically added by DocxXMLEditor.
        """
        return f'''<w:r>
  <w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>
  <w:commentReference w:id="{comment_id}"/>
</w:r>'''

    # ==================== Private: Metadata Updates ====================

    def _has_relationship(self, editor, target):
        """Check if a relationship with given target exists."""
        for rel_elem in editor.dom.getElementsByTagName("Relationship"):
            if rel_elem.getAttribute("Target") == target:
                return True
        return False

    def _has_override(self, editor, part_name):
        """Check if an override with given part name exists."""
        for override_elem in editor.dom.getElementsByTagName("Override"):
            if override_elem.getAttribute("PartName") == part_name:
                return True
        return False

    def _has_author(self, editor, author):
        """Check if an author already exists in people.xml."""
        for person_elem in editor.dom.getElementsByTagName("w15:person"):
            if person_elem.getAttribute("w15:author") == author:
                return True
        return False

    def _add_author_to_people(self, author):
        """Add author to people.xml (called during initialization)."""
        people_path = self.word_path / "people.xml"

        # people.xml should already exist from _setup_tracking
        if not people_path.exists():
            raise ValueError("people.xml should exist after _setup_tracking")

        editor = self["word/people.xml"]
        root = editor.get_node(tag="w15:people")

        # Check if author already exists
        if self._has_author(editor, author):
            return

        # Add author with proper XML escaping to prevent injection
        escaped_author = html.escape(author, quote=True)
        person_xml = f'''<w15:person w15:author="{escaped_author}">
  <w15:presenceInfo w15:providerId="None" w15:userId="{escaped_author}"/>
</w15:person>'''
        editor.append_to(root, person_xml)

    # The four comment parts: file name, relationship type, content type.
    # Each is wired up on its own, since documents from docx-js or pandoc ship
    # comments.xml already related but none of the other three.
    COMMENT_PARTS = (
        (
            "comments.xml",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
        ),
        (
            "commentsExtended.xml",
            "http://schemas.microsoft.com/office/2011/relationships/commentsExtended",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml",
        ),
        (
            "commentsIds.xml",
            "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsIds+xml",
        ),
        (
            "commentsExtensible.xml",
            "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtensible+xml",
        ),
    )

    def _ensure_comment_relationships(self):
        """Relate every comment part that exists to document.xml, once."""
        editor = self["word/_rels/document.xml.rels"]
        root = editor.dom.documentElement
        root_tag = root.tagName  # type: ignore
        prefix = root_tag.split(":")[0] + ":" if ":" in root_tag else ""
        present = {r.getAttribute("Type") for r in editor.dom.getElementsByTagName(f"{prefix}Relationship")}
        for name, rel_type, _ in self.COMMENT_PARTS:
            if (self.word_path / name).exists() and rel_type not in present:
                rel_xml = f'<{prefix}Relationship Id="{editor.get_next_rid()}" Type="{rel_type}" Target="{name}"/>'
                editor.append_to(root, rel_xml)

    def _ensure_comment_content_types(self):
        """Declare the content type of every comment part that exists, once."""
        editor = self["[Content_Types].xml"]
        root = editor.dom.documentElement
        for name, _, content_type in self.COMMENT_PARTS:
            part = f"/word/{name}"
            if (self.word_path / name).exists() and not self._has_override(editor, part):
                editor.append_to(root, f'<Override PartName="{part}" ContentType="{content_type}"/>')

    # ==================== Private: Resolving tracked changes ====================

    def _story_parts(self):
        """Parts that can hold tracked changes and exist in this document."""
        names = ["word/document.xml", "word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"]
        names += sorted(
            f"word/{p.name}"
            for pattern in ("header*.xml", "footer*.xml")
            for p in self.word_path.glob(pattern)
        )
        return [n for n in names if (self.unpacked_path / n).exists()]

    def _resolve_all(self, accept):
        # Edits made so far must be tracked: once resolved, nothing could tell
        for editor in self._editors.values():
            editor.save()
        if not RedliningValidator(
            self.unpacked_path, self.original_docx, verbose=False, author=self.author
        ).validate():
            raise ValueError(
                "Untracked edits were made before resolving tracked changes; see above."
            )
        for part in self._story_parts():
            self[part]._resolve_changes(accept)
        # Later edits are checked against the resolved document
        for editor in self._editors.values():
            editor.save()
        pack_document(self.unpacked_path, self.original_docx, validate=False)
