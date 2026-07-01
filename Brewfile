# System tools for the document skills.
# macOS: run `brew bundle` from this directory. Verify anytime with `brew bundle check`.
# Cautious mode: `brew bundle --no-upgrade` installs what is missing without upgrading anything you already have.
# Linux: see the System Tools table in AGENTS.md for apt-get equivalents.

# Homebrew filters PATH while it runs, so a plain `command -v` would miss tools
# installed by nvm, curl installers, and the like. The user's real PATH is kept
# in HOMEBREW_PATH, so we look there.
def on_path?(tool)
  ENV.fetch("HOMEBREW_PATH", ENV.fetch("PATH", "")).split(":").any? do |dir|
    File.executable?(File.join(dir, tool))
  end
end

# Runtimes. Guarded so an existing install from any source is respected.
brew "uv"   unless on_path?("uv")
brew "node" unless on_path?("node")

# Required by the skills
brew "poppler"        # pdftoppm, pdftotext, pdfimages (pdf, pptx, docx)
brew "pandoc"         # docx text extraction
cask "libreoffice"    # soffice (pptx, xlsx, docx)

# Optional. Uncomment what you need.
# brew "tesseract"      # OCR for scanned PDFs
# brew "tesseract-lang" # OCR language packs
# brew "qpdf"           # command-line PDF recipes in pdf/SKILL.md
# brew "coreutils"      # gtimeout, lets recalc.py enforce its timeout on macOS
