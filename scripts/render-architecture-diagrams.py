#!/usr/bin/env python3
"""Render the architecture's Mermaid sources into self-contained SVG images.

Build-time dependencies: playwright==1.62.0 and its Chromium headless shell.
The documentation site itself needs no JavaScript diagram dependencies.
"""

import hashlib
from pathlib import Path
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DIAGRAMS = ROOT / "docs" / "architecture" / "diagrams"
VERSION = "11.17.2"
URL = f"https://cdn.jsdelivr.net/npm/mermaid@{VERSION}/dist/mermaid.min.js"
SHA256 = "581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8"


def mermaid_bundle():
    cache = Path(tempfile.gettempdir()) / f"shake-cloud-mermaid-{VERSION}.min.js"
    if cache.exists():
        data = cache.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=30) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("Mermaid bundle checksum mismatch; refusing to execute it")
    return data.decode("utf-8")


def main():
    bundle = mermaid_bundle()
    sources = sorted(DIAGRAMS.glob("*.mmd"))
    if not sources:
        raise RuntimeError("No architecture Mermaid sources found")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.set_content('<!doctype html><html lang="ja"><body></body></html>')
        page.add_script_tag(content=bundle)
        page.evaluate("""() => mermaid.initialize({
            startOnLoad: false,
            securityLevel: 'strict',
            theme: 'default',
            htmlLabels: false,
            deterministicIds: true,
            deterministicIDSeed: 'shake-cloud-architecture',
            fontFamily: 'Noto Sans CJK JP, Noto Sans JP, sans-serif',
            flowchart: { htmlLabels: false, useMaxWidth: false, curve: 'linear' }
        })""")
        for source in sources:
            rendered = page.evaluate("""async ({id, source}) => {
                const {svg} = await mermaid.render(id, source);
                const container = document.createElement('div');
                container.innerHTML = svg;
                return new XMLSerializer().serializeToString(container.firstElementChild);
            }""", {"id": f"diagram-{source.stem}", "source": source.read_text()})
            root = ET.fromstring(rendered)
            if any(element.tag.endswith("foreignObject") for element in root.iter()):
                raise RuntimeError(f"{source.name}: HTML labels would not render on GitHub")
            source.with_suffix(".svg").write_text(rendered + "\n")
            print(f"Rendered {source.name} -> {source.with_suffix('.svg').name}")
        browser.close()


if __name__ == "__main__":
    main()
