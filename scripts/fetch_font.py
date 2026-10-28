"""Fetch an OFL-licensed Noto Sans SC subset for the actual site copy."""
from pathlib import Path
import re
import requests

root = Path(__file__).resolve().parents[1] / "docs"
copy = "".join(p.read_text() for p in root.iterdir() if p.suffix in (".html", ".js"))
text = "".join(sorted(set(re.findall(r"[\u3400-\u9fff]", copy) + list("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!? /%-+·→↗↓—（）[]:;×"))))
response = requests.get("https://fonts.googleapis.com/css2", params={"family": "Noto Sans SC:wght@100..900",
    "display": "swap", "text": text}, headers={"User-Agent": "Mozilla/5.0 Chrome/130.0.0.0 Safari/537.36"}, timeout=45)
response.raise_for_status()
target = root / "assets/fonts"
target.mkdir(parents=True, exist_ok=True)
faces = re.findall(r"font-weight:\s*(\d+);.*?url\(([^)]+)\)", response.text, re.S)
rules = []
for weight in ("400", "600", "700"):
    url = next(url for w, url in faces if w == weight)
    font = requests.get(url, timeout=45)
    font.raise_for_status()
    (target / f"site-sans-{weight}.ttf").write_bytes(font.content)
    rules.append(f"@font-face{{font-family:SiteSans;src:url('assets/fonts/site-sans-{weight}.ttf') format('truetype');font-weight:{weight};font-display:swap}}")
style = root / "style.css"
css = re.sub(r"^@font-face[^\n]*\n", "", style.read_text())
style.write_text("\n".join(rules) + "\n" + css)
(target / "site-sans.woff2").unlink(missing_ok=True)
license = requests.get("https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/OFL.txt", timeout=30)
license.raise_for_status()
(target / "OFL.txt").write_text(license.text)
print("Font subset:", len(text), "characters; three explicit weights")
