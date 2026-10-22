"""Gera a imagem de preview (Open Graph) de um roteiro a partir da própria capa da página.

Uso: python scripts/capa_og.py <pasta-do-roteiro> [<pasta> ...]
Para cada pasta: abre <pasta>/index.html num Chromium (1200x630), recorta só a capa
(mesmas fontes, título, foto e cores), grava <pasta>/capa.jpg e aponta og:image /
twitter:image para capa.jpg?v=<carimbo>. Sem capa reconhecível, a pasta é pulada.
Roda no GitHub Actions (.github/workflows/capa-og.yml).
"""
import asyncio, re, sys, time
from pathlib import Path
from playwright.async_api import async_playwright

BASE = 'https://roteiros.clubedoviajante.com.br'
W, H = 1200, 630

# Modelo atual (template/index.html): <header class="cover" id="topo">
CSS_ATUAL = """
nav.bar, main, footer { display:none !important }
html, body { margin:0 !important; overflow:hidden !important }
#topo { width:1200px !important; height:630px !important; min-height:630px !important; box-sizing:border-box }
#topo .wrap { max-width:none !important; height:630px !important; min-height:630px !important; box-sizing:border-box;
  padding:56px 72px 60px !important; justify-content:flex-end !important; gap:20px !important }
#topo h1 { font-size:96px !important }
#topo .sub { font-size:24px !important; max-width:none !important }
#topo .eyebrow { font-size:15px !important }
#topo .facts span { font-size:17px !important; padding:7px 14px !important }
"""
# Modelos antigos: <section class="hero"> (Barlow Condensed + Plus Jakarta Sans)
CSS_ANTIGO = """
html, body { margin:0 !important; overflow:hidden !important }
#topbar, .topbar { display:none !important }
section.hero { position:fixed !important; inset:0 !important; width:1200px !important; height:630px !important;
  min-height:630px !important; max-height:630px !important; margin:0 !important; z-index:2147483647 !important }
"""

async def gerar(pg, pasta: Path) -> bool:
    html = pasta / 'index.html'
    if not html.exists():
        return False
    await pg.goto(html.resolve().as_uri(), wait_until='networkidle', timeout=60000)
    if await pg.query_selector('#topo'):
        css, seletor = CSS_ATUAL, '#topo'
    elif await pg.query_selector('section.hero'):
        css, seletor = CSS_ANTIGO, 'section.hero'
    else:
        print(f'[capa-og] {pasta.name}: sem capa reconhecível, pulando')
        return False
    await pg.add_style_tag(content=css)
    # Deixa só a capa na tela: esconde tudo que não é a capa nem a contém
    await pg.evaluate("""sel => {
      const capa = document.querySelector(sel);
      let el = capa;
      while (el && el.parentElement) {
        for (const irmao of el.parentElement.children) if (irmao !== el) irmao.style.setProperty('display', 'none', 'important');
        el = el.parentElement;
      }
      const fundo = getComputedStyle(document.body).backgroundColor;
      if (!capa.style.backgroundColor) capa.style.backgroundColor = fundo && fundo !== 'rgba(0, 0, 0, 0)' ? fundo : '#1e2535';
    }""", seletor)
    await pg.evaluate('document.fonts.ready')
    await pg.wait_for_timeout(1200)
    await pg.screenshot(path=str(pasta / 'capa.jpg'), type='jpeg', quality=88,
                        clip={'x': 0, 'y': 0, 'width': W, 'height': H})
    apontar_og(html, pasta.name)
    print(f'[capa-og] {pasta.name}: capa gerada')
    return True

def apontar_og(html: Path, slug: str):
    s = html.read_text(encoding='utf-8')
    url = f'{BASE}/{slug}/capa.jpg?v={int(time.time())}'
    tags = ('og:image', 'og:image:secure_url', 'twitter:image')
    for t in tags:
        s = re.sub(r'(<meta\s+(?:property|name)="' + re.escape(t) + r'"\s+content=")[^"]*(")', r'\g<1>' + url + r'\g<2>', s)
    if 'property="og:image"' not in s:
        extra = (f'<meta property="og:image" content="{url}"/>\n'
                 f'<meta property="og:image:width" content="{W}"/>\n'
                 f'<meta property="og:image:height" content="{H}"/>\n'
                 f'<meta name="twitter:card" content="summary_large_image"/>\n'
                 f'<meta name="twitter:image" content="{url}"/>\n')
        s = re.sub(r'</head>', lambda m: extra + '</head>', s, count=1, flags=re.I)
    s = re.sub(r'(<meta\s+property="og:image:type"\s+content=")[^"]*(")', r'\g<1>image/jpeg\g<2>', s)
    html.write_text(s, encoding='utf-8')

async def main(pastas):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': W, 'height': H}, device_scale_factor=1, color_scheme='dark')
        feitos = 0
        for nome in pastas:
            pasta = Path(nome)
            if pasta.name in ('template', 'assets', 'scripts', '.github') or not pasta.is_dir():
                continue
            try:
                feitos += await gerar(pg, pasta)
            except Exception as e:
                print(f'[capa-og] {pasta.name}: falhou ({e})')
        await b.close()
        print(f'[capa-og] {feitos} capa(s) gerada(s)')

if __name__ == '__main__':
    asyncio.run(main(sys.argv[1:]))
