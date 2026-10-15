/**
 * html2pptx: turn an HTML slide into a PptxGenJS slide with positioned, editable elements.
 *
 *   const pptxgen = require('pptxgenjs');
 *   const html2pptx = require('<skill>/scripts/html2pptx.js');
 *
 *   const pptx = new pptxgen();
 *   pptx.layout = 'LAYOUT_16x9';                     // must match the HTML body size
 *   const { slide, placeholders } = await html2pptx('slide.html', pptx);
 *   slide.addChart(pptx.charts.LINE, data, placeholders[0]);
 *   await pptx.writeFile({ fileName: 'deck.pptx' });
 *
 * Run with NODE_PATH=<skill>/node_modules so the script's own require('pptxgenjs')
 * resolves. One browser is shared by every call and closes itself after a second
 * idle; html2pptx.close() closes it at once.
 *
 * All validation problems in a slide are collected and thrown together as one
 * Error, prefixed with the HTML file name. See html2pptx.md for the rules.
 *
 * Returns { slide, placeholders }, placeholders being [{ id, x, y, w, h }] in inches,
 * plus image when screenshotPlaceholders is set.
 */

const path = require('path');
const { pathToFileURL, fileURLToPath } = require('url');
const { chromium } = require('playwright-core');
const JSZip = require('jszip');

const PT_PER_PX = 0.75;
const PX_PER_IN = 96;
const EMU_PER_IN = 914400;
const IDLE_CLOSE_MS = 1000;

// ---------------------------------------------------------------------------
// Browser: launched once, shared by concurrent and successive calls.

let browserPromise = null;
let idleTimer = null;
let activeCalls = 0;

async function launchBrowser(tmpDir) {
  const env = { ...process.env, TMPDIR: tmpDir };
  // The Chrome already on the machine first; Playwright's Chromium only if someone installed it.
  const failures = [];
  for (const extra of [{ channel: 'chrome' }, {}]) {
    try {
      return await chromium.launch({ env, ...extra });
    } catch (e) {
      failures.push(`  ${extra.channel || 'Playwright Chromium'}: ${e.message.split('\n')[0]}`);
    }
  }
  throw new Error(
    'No browser available to render HTML. Install Google Chrome, or on a machine without it run ' +
    `\`npx playwright-core install chromium\` in ${path.dirname(__dirname)} once.\n${failures.join('\n')}`
  );
}

async function acquireBrowser(tmpDir) {
  clearTimeout(idleTimer);
  activeCalls++;
  if (!browserPromise) browserPromise = launchBrowser(tmpDir);
  try {
    return await browserPromise;
  } catch (e) {
    browserPromise = null;
    activeCalls--;
    throw e;
  }
}

function releaseBrowser() {
  activeCalls--;
  if (activeCalls === 0) idleTimer = setTimeout(close, IDLE_CLOSE_MS);
}

async function close() {
  clearTimeout(idleTimer);
  const pending = browserPromise;
  browserPromise = null;
  const browser = pending && (await pending.catch(() => null));
  if (browser) await browser.close();
}

// ---------------------------------------------------------------------------
// Output repair. PptxGenJS writes a few constructs the OOXML schema rejects;
// each fix below rewrites one of them into its valid equivalent when the
// presentation is written, so every deck html2pptx touches comes out valid.

const PARAGRAPH = /<a:p>([\s\S]*?)<\/a:p>/g;
const PARA_PROPS = /<a:pPr\b[^>]*?\/>|<a:pPr\b[^>]*>[\s\S]*?<\/a:pPr>/g;

/**
 * PptxGenJS writes an <a:pPr> before every text run, so a paragraph with mixed
 * formatting gets several; the schema allows one, first. Paragraph properties
 * are identical on every run html2pptx emits, so the first is kept. The
 * bullet size of 100% it adds is the default, and its integer form fails the
 * schema, so it is dropped.
 */
function fixParagraphProperties(xml) {
  return xml.replace(/<a:buSzPct val="100000"\/>/g, '').replace(PARAGRAPH, (whole, body) => {
    const props = body.match(PARA_PROPS);
    if (!props || (props.length === 1 && body.startsWith(props[0]))) return whole;
    return `<a:p>${props[0]}${body.replace(PARA_PROPS, '')}</a:p>`;
  });
}

/** <p:notesMasterIdLst> belongs straight after <p:sldMasterIdLst>; PptxGenJS puts it last. */
function fixPresentationOrder(xml) {
  const match = xml.match(/<p:notesMasterIdLst>[\s\S]*?<\/p:notesMasterIdLst>/);
  if (!match) return xml;
  return xml.replace(match[0], '').replace('</p:sldMasterIdLst>', `</p:sldMasterIdLst>${match[0]}`);
}

/**
 * Chart XML: 2-D charts take exactly two axis ids (PptxGenJS adds a third);
 * a line chart's <c:grouping> is required; only bar and bubble series carry
 * <c:invertIfNegative>; a series' <c:marker> precedes its data labels; and
 * value axes, which scatter charts use for X, have none of the category-axis
 * settings PptxGenJS writes into them.
 */
function markerFirst(series) {
  const marker = series.match(/<c:marker>[\s\S]*?<\/c:marker>/);
  const labels = series.indexOf('<c:dLbls>');
  if (!marker || labels < 0 || labels > marker.index) return series;
  const rest = series.replace(marker[0], '');
  return rest.slice(0, labels) + marker[0] + rest.slice(labels);
}

function fixChart(xml) {
  return xml
    .replace(/<c:(barChart|lineChart|areaChart|radarChart|scatterChart)>([\s\S]*?)<\/c:\1>/g, (whole, type, body) => {
      let count = 0;
      body = body.replace(/<c:axId val="\d+"\/>/g, (axis) => (++count > 2 ? '' : axis));
      if (type !== 'barChart') body = body.replace(/\s*<c:invertIfNegative val="\d"\/>/g, '');
      if (type === 'lineChart' && !/^\s*<c:grouping/.test(body)) body = `<c:grouping val="standard"/>${body}`;
      body = body.replace(/<c:ser>[\s\S]*?<\/c:ser>/g, markerFirst);
      return `<c:${type}>${body}</c:${type}>`;
    })
    .replace(/<c:valAx>[\s\S]*?<\/c:valAx>/g, (axis) =>
      axis.replace(/\s*<c:(auto|lblAlgn|lblOffset|noMultiLvlLbl|tickLblSkip|tickMarkSkip) val="[^"]*"\/>/g, ''));
}

/** Relationship targets relative to their source part, as Office writes them. */
function fixAbsoluteTargets(xml, name) {
  const sourceDir = '/' + path.posix.dirname(path.posix.dirname(name)).replace(/^\.$/, '');
  return xml.replace(/<Relationship\b[^>]*\/>/g, (rel) => {
    if (/TargetMode="External"/.test(rel)) return rel;
    return rel.replace(/Target="(\/[^"]*)"/, (attr, target) =>
      `Target="${path.posix.relative(sourceDir, target)}"`);
  });
}

const FIXES = [
  [/^ppt\/(slides|slideLayouts|slideMasters|notesSlides|notesMasters)\/[^/]+\.xml$/, fixParagraphProperties],
  [/^ppt\/presentation\.xml$/, fixPresentationOrder],
  [/^ppt\/charts\/[^/]+\.xml$/, fixChart],
  [/\.rels$/, fixAbsoluteTargets]
];

function ensureValidOutput(pres) {
  if (pres.__html2pptxPatched || typeof pres.exportPresentation !== 'function') return;
  const exportPresentation = pres.exportPresentation;
  pres.exportPresentation = async (props = {}) => {
    const zip = await JSZip.loadAsync(await exportPresentation({ ...props, outputType: 'nodebuffer' }));
    for (const name of Object.keys(zip.files)) {
      const fixes = FIXES.filter(([pattern]) => pattern.test(name)).map(([, fix]) => fix);
      if (!fixes.length || zip.files[name].dir) continue;
      const xml = await zip.file(name).async('string');
      const fixed = fixes.reduce((text, fix) => fix(text, name), xml);
      if (fixed !== xml) zip.file(name, fixed);
    }
    const type = !props.outputType || props.outputType === 'STREAM' ? 'nodebuffer' : props.outputType;
    return zip.generateAsync({ type, compression: props.compression ? 'DEFLATE' : 'STORE' });
  };
  pres.__html2pptxPatched = true;
}

// ---------------------------------------------------------------------------
// Validation that needs the rendered page or the presentation.

async function getBodyDimensions(page) {
  const body = await page.evaluate(() => {
    const style = window.getComputedStyle(document.body);
    return {
      width: parseFloat(style.width),
      height: parseFloat(style.height),
      scrollWidth: document.body.scrollWidth,
      scrollHeight: document.body.scrollHeight,
      quirks: document.compatMode === 'BackCompat'
    };
  });

  // Without a doctype the browser uses quirks mode, where the body reports the
  // viewport's size, so every overflow figure below would be wrong.
  if (body.quirks) {
    return { ...body, errors: ['Start the file with <!DOCTYPE html>. Without it the page is laid out in quirks mode and cannot be measured.'] };
  }

  const errors = [];
  const widthOverflowPt = Math.max(0, body.scrollWidth - body.width - 1) * PT_PER_PX;
  const heightOverflowPt = Math.max(0, body.scrollHeight - body.height - 1) * PT_PER_PX;
  if (widthOverflowPt > 0 || heightOverflowPt > 0) {
    const directions = [];
    if (widthOverflowPt > 0) directions.push(`${widthOverflowPt.toFixed(1)}pt horizontally`);
    if (heightOverflowPt > 0) directions.push(`${heightOverflowPt.toFixed(1)}pt vertically`);
    const reminder = heightOverflowPt > 0 ? ' (leave a 0.5" margin at the bottom of the slide)' : '';
    errors.push(`HTML content overflows body by ${directions.join(' and ')}${reminder}`);
  }
  return { ...body, errors };
}

function validateDimensions(body, pres) {
  if (!pres.presLayout) return [];
  const widthIn = body.width / PX_PER_IN;
  const heightIn = body.height / PX_PER_IN;
  const layoutWidth = pres.presLayout.width / EMU_PER_IN;
  const layoutHeight = pres.presLayout.height / EMU_PER_IN;
  if (Math.abs(layoutWidth - widthIn) > 0.1 || Math.abs(layoutHeight - heightIn) > 0.1) {
    return [
      `HTML dimensions (${widthIn.toFixed(1)}" × ${heightIn.toFixed(1)}") ` +
      `don't match presentation layout (${layoutWidth.toFixed(1)}" × ${layoutHeight.toFixed(1)}")`
    ];
  }
  return [];
}

function runText(el) {
  const runs = Array.isArray(el.text) ? el.text : el.items || [];
  return runs.map((r) => r.text).join('');
}

function validateTextBoxPosition(slideData, body) {
  const errors = [];
  const slideHeightIn = body.height / PX_PER_IN;
  const minBottomMargin = 0.5;
  for (const el of slideData.elements) {
    if (!['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'list'].includes(el.type)) continue;
    const distance = slideHeightIn - (el.position.y + el.position.h);
    if ((el.style?.fontSize || 0) > 12 && distance < minBottomMargin) {
      const text = runText(el);
      errors.push(
        `Text box "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}" ends too close to bottom edge ` +
        `(${distance.toFixed(2)}" from bottom, minimum ${minBottomMargin}" for text over 12pt)`
      );
    }
  }
  return errors;
}

// ---------------------------------------------------------------------------
// Building the slide.

/** A local file path for a file:// URL, the data for a data: URL, or the URL itself. */
function imageSource(url) {
  if (url.startsWith('file:')) return { path: fileURLToPath(url) };
  if (url.startsWith('data:')) return { data: url.slice('data:'.length) };
  return { path: url };
}

function addBackground(slideData, targetSlide) {
  const bg = slideData.background;
  if (bg.type === 'image' && bg.path) targetSlide.background = imageSource(bg.path);
  else if (bg.type === 'color' && bg.value) targetSlide.background = { color: bg.value };
}

function addElements(slideData, targetSlide, pres) {
  for (const el of slideData.elements) {
    if (el.type === 'image') {
      const source = el.data ? { data: el.data } : el.src ? imageSource(el.src) : null;
      if (!source) throw new Error('Image element missing src/data');
      targetSlide.addImage({ ...source, ...el.position });
    } else if (el.type === 'line') {
      targetSlide.addShape(pres.ShapeType.line, {
        x: el.x1,
        y: el.y1,
        w: el.x2 - el.x1,
        h: el.y2 - el.y1,
        line: { color: el.color, width: el.width }
      });
    } else if (el.type === 'shape') {
      const options = {
        ...el.position,
        shape: el.shape.rectRadius > 0 ? pres.ShapeType.roundRect : pres.ShapeType.rect
      };
      if (el.shape.fill) {
        options.fill = { color: el.shape.fill };
        if (el.shape.transparency != null) options.fill.transparency = el.shape.transparency;
      }
      if (el.shape.line) options.line = el.shape.line;
      if (el.shape.rectRadius > 0) options.rectRadius = el.shape.rectRadius;
      if (el.shape.shadow) options.shadow = el.shape.shadow;
      targetSlide.addText('', options);
    } else if (el.type === 'list') {
      targetSlide.addText(el.items, {
        ...el.position,
        fontSize: el.style.fontSize,
        fontFace: el.style.fontFace,
        color: el.style.color,
        align: el.style.align,
        valign: 'top',
        lineSpacing: el.style.lineSpacing,
        paraSpaceBefore: el.style.paraSpaceBefore,
        paraSpaceAfter: el.style.paraSpaceAfter,
        margin: el.style.margin
      });
    } else {
      // Browsers measure single-line text slightly narrower than PowerPoint does,
      // so widen one-line boxes by 2% on the side away from the alignment.
      const lineHeight = el.style.lineSpacing || el.style.fontSize * 1.2;
      const isSingleLine = el.position.h * 72 <= lineHeight * 1.5;
      let { x, w } = el.position;
      if (isSingleLine) {
        const extra = w * 0.02;
        if (el.style.align === 'center') x -= extra / 2;
        else if (el.style.align === 'right') x -= extra;
        w += extra;
      }

      // Bold, italic, underline and colour live on the runs only: PptxGenJS
      // copies any shape-level option onto runs where it is falsy, which
      // would re-bold a deliberately normal-weight span.
      const options = {
        x,
        y: el.position.y,
        w,
        h: el.position.h,
        fontSize: el.style.fontSize,
        fontFace: el.style.fontFace,
        valign: 'top',
        lineSpacing: el.style.lineSpacing,
        paraSpaceBefore: el.style.paraSpaceBefore,
        paraSpaceAfter: el.style.paraSpaceAfter,
        inset: 0
      };
      if (el.style.align) options.align = el.style.align;
      if (el.style.margin) options.margin = el.style.margin;
      if (el.style.rotate !== undefined) options.rotate = el.style.rotate;
      targetSlide.addText(el.text, options);
    }
  }
}

// Runs in the page: reads the rendered DOM into slide data.
async function extractSlideData(page) {
  return await page.evaluate(() => {
    const PT_PER_PX = 0.75;
    const PX_PER_IN = 96;
    // Single-weight fonts: PowerPoint would fake bold, making the text wider.
    const SINGLE_WEIGHT_FONTS = ['impact'];
    const MANUAL_BULLET = /^[•\-\*▪▸○●◆◇■□]\s/;
    const NUMBER_STYLES = {
      'lower-alpha': 'alphaLcPeriod',
      'lower-latin': 'alphaLcPeriod',
      'upper-alpha': 'alphaUcPeriod',
      'upper-latin': 'alphaUcPeriod',
      'lower-roman': 'romanLcPeriod',
      'upper-roman': 'romanUcPeriod'
    };

    const errors = [];
    const firstFamily = (fontFamily) => fontFamily.split(',')[0].replace(/['"]/g, '').trim();
    const skipBold = (fontFamily) => SINGLE_WEIGHT_FONTS.includes(firstFamily(fontFamily).toLowerCase());
    const isBold = (computed) => computed.fontWeight === 'bold' || parseInt(computed.fontWeight) >= 600;
    const pxToInch = (px) => px / PX_PER_IN;
    const pxToPoints = (pxStr) => parseFloat(pxStr) * PT_PER_PX;
    const rgbToHex = (rgbStr) => {
      if (rgbStr === 'rgba(0, 0, 0, 0)' || rgbStr === 'transparent') return 'FFFFFF';
      const match = rgbStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
      if (!match) return 'FFFFFF';
      return match.slice(1).map((n) => parseInt(n).toString(16).padStart(2, '0')).join('');
    };
    const extractAlpha = (rgbStr) => {
      const match = rgbStr.match(/rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)/);
      if (!match || !match[4]) return null;
      return Math.round((1 - parseFloat(match[4])) * 100);
    };
    const applyTextTransform = (text, transform) => {
      if (transform === 'uppercase') return text.toUpperCase();
      if (transform === 'lowercase') return text.toLowerCase();
      if (transform === 'capitalize') return text.replace(/\b\w/g, (c) => c.toUpperCase());
      return text;
    };
    const box = (rect) => ({
      x: pxToInch(rect.left),
      y: pxToInch(rect.top),
      w: pxToInch(rect.width),
      h: pxToInch(rect.height)
    });

    const getRotation = (transform, writingMode) => {
      // PowerPoint: 90° reads top to bottom, 270° bottom to top.
      let angle = writingMode === 'vertical-rl' ? 90 : writingMode === 'vertical-lr' ? 270 : 0;
      if (transform && transform !== 'none') {
        const rotateMatch = transform.match(/rotate\((-?\d+(?:\.\d+)?)deg\)/);
        const matrixMatch = transform.match(/matrix\(([^)]+)\)/);
        if (rotateMatch) {
          angle += parseFloat(rotateMatch[1]);
        } else if (matrixMatch) {
          const values = matrixMatch[1].split(',').map(parseFloat);
          angle += Math.round(Math.atan2(values[1], values[0]) * (180 / Math.PI));
        }
      }
      angle = ((angle % 360) + 360) % 360;
      return angle === 0 ? null : angle;
    };

    // PowerPoint rotates the unrotated box, while the browser reports the rotated one.
    const getPositionAndSize = (el, rect, rotation) => {
      if (rotation === null) return { x: rect.left, y: rect.top, w: rect.width, h: rect.height };
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      if (rotation === 90 || rotation === 270) {
        return { x: centerX - rect.height / 2, y: centerY - rect.width / 2, w: rect.height, h: rect.width };
      }
      return {
        x: centerX - el.offsetWidth / 2,
        y: centerY - el.offsetHeight / 2,
        w: el.offsetWidth,
        h: el.offsetHeight
      };
    };

    const parseBoxShadow = (boxShadow) => {
      // Computed form: "rgba(0, 0, 0, 0.3) 2px 2px 8px 0px [inset]". Inset shadows
      // have no PowerPoint equivalent and corrupt the file, so they are skipped.
      if (!boxShadow || boxShadow === 'none' || /inset/.test(boxShadow)) return null;
      const colorMatch = boxShadow.match(/rgba?\([^)]+\)/);
      const parts = boxShadow.match(/([-\d.]+)(px|pt)/g);
      if (!parts || parts.length < 2) return null;
      const offsetX = parseFloat(parts[0]);
      const offsetY = parseFloat(parts[1]);
      const blur = parts.length > 2 ? parseFloat(parts[2]) : 0;
      let angle = 0;
      if (offsetX !== 0 || offsetY !== 0) {
        angle = Math.atan2(offsetY, offsetX) * (180 / Math.PI);
        if (angle < 0) angle += 360;
      }
      let opacity = 0.5;
      const opacityMatch = colorMatch && colorMatch[0].match(/[\d.]+\)$/);
      if (opacityMatch) opacity = parseFloat(opacityMatch[0]);
      return {
        type: 'outer',
        angle: Math.round(angle),
        blur: blur * 0.75,
        color: colorMatch ? rgbToHex(colorMatch[0]) : '000000',
        offset: Math.sqrt(offsetX * offsetX + offsetY * offsetY) * PT_PER_PX,
        opacity
      };
    };

    // Formatting of a run, from the computed style of the element holding its text.
    const runOptions = (element, underlined) => {
      const computed = window.getComputedStyle(element);
      const options = {
        fontFace: firstFamily(computed.fontFamily),
        fontSize: pxToPoints(computed.fontSize),
        color: rgbToHex(computed.color)
      };
      if (isBold(computed) && !skipBold(computed.fontFamily)) options.bold = true;
      if (computed.fontStyle === 'italic') options.italic = true;
      if (underlined) options.underline = { style: 'sng' };
      if (computed.textDecorationLine.includes('line-through')) options.strike = 'sngStrike';
      if (computed.verticalAlign === 'super') options.superscript = true;
      if (computed.verticalAlign === 'sub') options.subscript = true;
      const transparency = extractAlpha(computed.color);
      if (transparency !== null) options.transparency = transparency;
      const spacing = parseFloat(computed.letterSpacing);
      if (spacing) options.charSpacing = spacing * PT_PER_PX;
      return { options, transform: computed.textTransform };
    };

    const INLINE_TAGS = ['B', 'STRONG', 'I', 'EM', 'U', 'S', 'SPAN', 'SUP', 'SUB', 'A', 'CODE', 'SMALL', 'MARK'];

    // Text runs of a text element, one per stretch of uniform formatting.
    // <br> becomes a line break inside the paragraph. Nested lists are skipped:
    // they are paragraphs of their own.
    const parseRuns = (element) => {
      const runs = [];
      let breakPending = false;
      const walk = (node, underlined) => {
        node.childNodes.forEach((child) => {
          if (child.nodeType === Node.TEXT_NODE) {
            let text = child.textContent.replace(/\s+/g, ' ');
            if (!text) return;
            const { options, transform } = runOptions(child.parentElement, underlined);
            if (breakPending) {
              text = text.replace(/^\s+/, '');
              if (!text) return;
              options.softBreakBefore = true;
              breakPending = false;
            }
            runs.push({ text: applyTextTransform(text, transform), options });
          } else if (child.nodeType === Node.ELEMENT_NODE) {
            if (child.tagName === 'BR') {
              if (runs.length) runs[runs.length - 1].text = runs[runs.length - 1].text.replace(/\s+$/, '');
              if (breakPending) runs.push({ text: '', options: { softBreakBefore: true } });
              breakPending = runs.length > 0;
              return;
            }
            if (child.tagName === 'UL' || child.tagName === 'OL') return;
            if (INLINE_TAGS.includes(child.tagName)) {
              const computed = window.getComputedStyle(child);
              for (const side of ['Left', 'Right', 'Top', 'Bottom']) {
                if (parseFloat(computed[`margin${side}`]) > 0) {
                  errors.push(
                    `Inline element <${child.tagName.toLowerCase()}> has margin-${side.toLowerCase()}, ` +
                    'which PowerPoint text runs cannot represent. Remove margins from inline elements.'
                  );
                }
              }
            }
            walk(child, underlined || window.getComputedStyle(child).textDecorationLine.includes('underline'));
          }
        });
      };
      walk(element, window.getComputedStyle(element).textDecorationLine.includes('underline'));
      if (runs.length) {
        runs[0].text = runs[0].text.replace(/^\s+/, '');
        runs[runs.length - 1].text = runs[runs.length - 1].text.replace(/\s+$/, '');
      }
      return runs.filter((r) => r.text.length > 0 || r.options.softBreakBefore);
    };

    // Background of the slide: an image or a colour.
    const bodyStyle = window.getComputedStyle(document.body);
    const bgImage = bodyStyle.backgroundImage;
    if (bgImage && (bgImage.includes('linear-gradient') || bgImage.includes('radial-gradient'))) {
      errors.push(
        'CSS gradients are not supported. Rasterize the gradient to a PNG with Sharp first, ' +
        "then use background-image: url('gradient.png')"
      );
    }
    const urlMatch = bgImage && bgImage !== 'none' && bgImage.match(/url\(["']?([^"')]+)["']?\)/);
    const background = urlMatch
      ? { type: 'image', path: urlMatch[1] }
      : { type: 'color', value: rgbToHex(bodyStyle.backgroundColor) };

    const elements = [];
    const placeholders = [];
    const textTags = ['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'UL', 'OL', 'LI'];
    const processed = new Set();
    let renderIdCounter = 0;

    document.querySelectorAll('*').forEach((el) => {
      if (processed.has(el)) return;

      // Font Awesome renders <i class="fa-…"> as inline SVG; screenshot it into a PNG.
      if (el.tagName.toLowerCase() === 'svg' &&
          (el.classList.contains('svg-inline--fa') || el.hasAttribute('data-fa-i2svg'))) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          const renderId = `fa-svg-${renderIdCounter++}`;
          el.setAttribute('data-html2pptx-render-id', renderId);
          elements.push({ type: 'image', renderId, position: box(rect) });
          processed.add(el);
          return;
        }
      }

      if (textTags.includes(el.tagName)) {
        const computed = window.getComputedStyle(el);
        const hasBg = computed.backgroundColor && computed.backgroundColor !== 'rgba(0, 0, 0, 0)';
        const hasBorder = ['Top', 'Right', 'Bottom', 'Left']
          .some((side) => parseFloat(computed[`border${side}Width`]) > 0);
        const hasShadow = computed.boxShadow && computed.boxShadow !== 'none';
        if (hasBg || hasBorder || hasShadow) {
          errors.push(
            `Text element <${el.tagName.toLowerCase()}> has ${hasBg ? 'background' : hasBorder ? 'border' : 'shadow'}. ` +
            'Backgrounds, borders, and shadows are only supported on <div> elements, not text elements.'
          );
          return;
        }
      }

      if (el.classList && el.classList.contains('placeholder')) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
          errors.push(
            `Placeholder "${el.id || 'unnamed'}" has ${rect.width === 0 ? 'width: 0' : 'height: 0'}. Check the layout CSS.`
          );
        } else {
          placeholders.push({ id: el.id || `placeholder-${placeholders.length}`, ...box(rect) });
        }
        processed.add(el);
        return;
      }

      if (el.tagName === 'IMG') {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          elements.push({ type: 'image', src: el.src, position: box(rect) });
          processed.add(el);
          return;
        }
      }

      // A <div> with a background or border becomes a shape.
      if (el.tagName === 'DIV') {
        const computed = window.getComputedStyle(el);
        const hasBg = computed.backgroundColor && computed.backgroundColor !== 'rgba(0, 0, 0, 0)';

        for (const node of el.childNodes) {
          const text = node.nodeType === Node.TEXT_NODE ? node.textContent.trim() : '';
          if (text) {
            errors.push(
              `DIV element contains unwrapped text "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}". ` +
              'Wrap all text in <p>, <h1>-<h6>, <ul>, or <ol> tags; bare text does not appear in PowerPoint.'
            );
          }
        }

        if (computed.backgroundImage && computed.backgroundImage !== 'none') {
          errors.push(
            'Background images on DIV elements are not supported. ' +
            'Use an <img> element, or slide.addImage() in PptxGenJS, to layer images.'
          );
          return;
        }

        const sides = ['Top', 'Right', 'Bottom', 'Left'];
        const widths = sides.map((side) => parseFloat(computed[`border${side}Width`]) || 0);
        const hasBorder = widths.some((b) => b > 0);
        const hasUniformBorder = hasBorder && widths.every((b) => b === widths[0]);

        if (hasBg || hasBorder) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            const { x, y, w, h } = box(rect);
            if (hasBg || hasUniformBorder) {
              const radius = computed.borderRadius;
              const radiusValue = parseFloat(radius);
              let rectRadius = 0;
              if (radiusValue) {
                // 50% or more is a circle; smaller percentages are of the shorter side.
                if (radius.includes('%')) {
                  rectRadius = radiusValue >= 50 ? 1 : (radiusValue / 100) * pxToInch(Math.min(rect.width, rect.height));
                } else {
                  rectRadius = radius.includes('pt') ? radiusValue / 72 : radiusValue / PX_PER_IN;
                }
              }
              elements.push({
                type: 'shape',
                position: { x, y, w, h },
                shape: {
                  fill: hasBg ? rgbToHex(computed.backgroundColor) : null,
                  transparency: hasBg ? extractAlpha(computed.backgroundColor) : null,
                  line: hasUniformBorder
                    ? { color: rgbToHex(computed.borderTopColor), width: pxToPoints(computed.borderTopWidth) }
                    : null,
                  rectRadius,
                  shadow: parseBoxShadow(computed.boxShadow)
                }
              });
            }
            // Partial borders become lines, inset by half their width to sit on the edge.
            if (hasBorder && !hasUniformBorder) {
              sides.forEach((side, i) => {
                if (!widths[i]) return;
                const widthPt = pxToPoints(computed[`border${side}Width`]);
                const inset = widthPt / 72 / 2;
                const color = rgbToHex(computed[`border${side}Color`]);
                const line = {
                  Top: [x, y + inset, x + w, y + inset],
                  Right: [x + w - inset, y, x + w - inset, y + h],
                  Bottom: [x, y + h - inset, x + w, y + h - inset],
                  Left: [x + inset, y, x + inset, y + h]
                }[side];
                elements.push({ type: 'line', x1: line[0], y1: line[1], x2: line[2], y2: line[3], width: widthPt, color });
              });
            }
            processed.add(el);
            return;
          }
        }
      }

      // A list, including nested lists, becomes one text box of bulleted or numbered paragraphs.
      if (el.tagName === 'UL' || el.tagName === 'OL') {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;

        const liElements = Array.from(el.querySelectorAll('li'));
        const paddingPt = pxToPoints(window.getComputedStyle(el).paddingLeft);
        // The list's left padding splits evenly into bullet position and text indent.
        const marginLeft = paddingPt * 0.5;
        const textIndent = paddingPt * 0.5;
        const items = [];

        liElements.forEach((li, idx) => {
          const list = li.parentElement;
          let level = 0;
          for (let p = list.parentElement; p && p !== el.parentElement; p = p.parentElement) {
            if (p.tagName === 'UL' || p.tagName === 'OL') level++;
          }
          const runs = parseRuns(li);
          if (!runs.length) return;
          runs[0].text = runs[0].text.replace(/^[•\-\*▪▸]\s*/, '');
          const bullet = { indent: textIndent };
          if (list.tagName === 'OL') {
            bullet.type = 'number';
            bullet.style = NUMBER_STYLES[window.getComputedStyle(list).listStyleType] || 'arabicPeriod';
            const siblings = Array.from(list.children).filter((c) => c.tagName === 'LI');
            bullet.numberStartAt = (list.start || 1) + siblings.indexOf(li);
          }
          runs[0].options.bullet = bullet;
          if (level) runs[0].options.indentLevel = level;
          if (idx < liElements.length - 1) runs[runs.length - 1].options.breakLine = true;
          items.push(...runs);
        });

        const computed = window.getComputedStyle(liElements[0] || el);
        elements.push({
          type: 'list',
          items,
          position: box(rect),
          style: {
            fontSize: pxToPoints(computed.fontSize),
            fontFace: firstFamily(computed.fontFamily),
            color: rgbToHex(computed.color),
            align: computed.textAlign === 'start' ? 'left' : computed.textAlign,
            lineSpacing: computed.lineHeight && computed.lineHeight !== 'normal' ? pxToPoints(computed.lineHeight) : null,
            paraSpaceBefore: 0,
            paraSpaceAfter: pxToPoints(computed.marginBottom),
            // PptxGenJS margin order is [left, right, bottom, top].
            margin: [marginLeft, 0, 0, 0]
          }
        });

        // Its items, nested lists and any text tags inside belong to this box.
        el.querySelectorAll('li, ul, ol, p, h1, h2, h3, h4, h5, h6').forEach((child) => processed.add(child));
        processed.add(el);
        return;
      }

      if (!textTags.includes(el.tagName)) return;

      const rect = el.getBoundingClientRect();
      const text = el.textContent.trim();
      if (rect.width === 0 || rect.height === 0 || !text) return;

      if (el.tagName !== 'LI' && MANUAL_BULLET.test(text)) {
        errors.push(
          `Text element <${el.tagName.toLowerCase()}> starts with bullet symbol "${text.substring(0, 20)}...". ` +
          'Use <ul> or <ol> lists instead of manual bullet symbols.'
        );
        return;
      }

      const computed = window.getComputedStyle(el);
      const rotation = getRotation(computed.transform, computed.writingMode);
      const { x, y, w, h } = getPositionAndSize(el, rect, rotation);
      const runs = parseRuns(el);

      const style = {
        fontSize: pxToPoints(computed.fontSize),
        fontFace: firstFamily(computed.fontFamily),
        align: computed.textAlign === 'start' ? 'left' : computed.textAlign,
        lineSpacing: pxToPoints(computed.lineHeight),
        paraSpaceBefore: pxToPoints(computed.marginTop),
        paraSpaceAfter: pxToPoints(computed.marginBottom),
        // PptxGenJS margin order is [left, right, bottom, top].
        margin: [
          pxToPoints(computed.paddingLeft),
          pxToPoints(computed.paddingRight),
          pxToPoints(computed.paddingBottom),
          pxToPoints(computed.paddingTop)
        ]
      };
      if (rotation !== null) style.rotate = rotation;
      // Line spacing follows the largest run, as the browser laid it out.
      if (style.lineSpacing) {
        const maxFontSize = Math.max(style.fontSize, ...runs.map((r) => r.options.fontSize || 0));
        if (maxFontSize > style.fontSize) style.lineSpacing *= maxFontSize / style.fontSize;
      }

      elements.push({
        type: el.tagName.toLowerCase(),
        text: runs,
        position: { x: pxToInch(x), y: pxToInch(y), w: pxToInch(w), h: pxToInch(h) },
        style
      });
      processed.add(el);
    });

    return { background, elements, placeholders, errors };
  });
}

/**
 * Options:
 *   slide                  an existing PptxGenJS slide to draw on (default: a new one)
 *   screenshotPlaceholders also capture each placeholder as a PNG, in placeholder.image,
 *                          for browser-rendered content such as Chart.js or SVG
 *   renderDelay            ms to wait before reading the page, for scripts that draw late
 *   tmpDir                 temporary directory for the browser
 */
async function html2pptx(htmlFile, pres, options = {}) {
  const {
    tmpDir = process.env.TMPDIR || '/tmp',
    slide = null,
    deviceScaleFactor = 3,
    screenshotPlaceholders = false,
    renderDelay = 0
  } = options;
  try {
    ensureValidOutput(pres);
    const filePath = path.resolve(htmlFile);
    const browser = await acquireBrowser(tmpDir);
    let body;
    let slideData;
    let page;
    try {
      page = await browser.newPage({ deviceScaleFactor });
      await page.goto(pathToFileURL(filePath).href);
      body = await getBodyDimensions(page);
      await page.setViewportSize({ width: Math.round(body.width), height: Math.round(body.height) });
      // Let local fonts load, and Font Awesome replace <i> with <svg>.
      await page.waitForSelector('svg[data-fa-i2svg], svg.svg-inline--fa', { timeout: 1000 }).catch(() => {});
      await page.evaluate(async () => {
        if (document.fonts && document.fonts.status !== 'loaded') await document.fonts.ready;
      });
      if (renderDelay) await page.waitForTimeout(renderDelay);
      slideData = await extractSlideData(page);
      if (screenshotPlaceholders) {
        for (const ph of slideData.placeholders) {
          const clip = { x: ph.x * PX_PER_IN, y: ph.y * PX_PER_IN, width: ph.w * PX_PER_IN, height: ph.h * PX_PER_IN };
          ph.image = `image/png;base64,${(await page.screenshot({ type: 'png', clip })).toString('base64')}`;
        }
      }
      for (const el of slideData.elements) {
        if (el.type !== 'image' || !el.renderId) continue;
        const png = await page.locator(`[data-html2pptx-render-id="${el.renderId}"]`)
          .screenshot({ type: 'png', omitBackground: true });
        el.data = `image/png;base64,${png.toString('base64')}`;
        delete el.renderId;
      }
    } finally {
      if (page) await page.close().catch(() => {});
      releaseBrowser();
    }

    const errors = [
      ...body.errors,
      ...validateDimensions(body, pres),
      ...validateTextBoxPosition(slideData, body),
      ...slideData.errors
    ];
    if (errors.length) {
      throw new Error(errors.length === 1
        ? errors[0]
        : `Multiple validation errors found:\n${errors.map((e, i) => `  ${i + 1}. ${e}`).join('\n')}`);
    }

    const targetSlide = slide || pres.addSlide();
    addBackground(slideData, targetSlide);
    addElements(slideData, targetSlide, pres);
    return { slide: targetSlide, placeholders: slideData.placeholders };
  } catch (error) {
    if (!error.message.startsWith(htmlFile)) error.message = `${htmlFile}: ${error.message}`;
    throw error;
  }
}

html2pptx.close = close;
module.exports = html2pptx;
