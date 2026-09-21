"""Page layout and PDF rendering, via Verovio.

Two things here are not obvious and cost real time to find.

`unit` is the staff-size knob, not `scale`.  Verovio's `unit` is half a staff
space in 1/10 mm, so a staff height of `mm` millimetres is `mm / 4 * 10 / 2`.
`scale` only zooms the finished SVG, so turning it up makes a big picture of a
small score.

cairosvg does not honour `@font-face`, so every SMuFL glyph Verovio draws as text
— chord-symbol accidentals above all — comes out as a tofu rectangle in the PDF
no matter what `smuflTextFont` is set to.  `install_smufl_font()` unpacks
Verovio's own Leipzig out of its stylesheet and installs it for fontconfig,
which is what cairosvg actually consults.
"""
import base64
import io
import os
import re
import subprocess

PAGE_LETTER = (215.9, 279.4)
PAGE_A4 = (210.0, 297.0)
PAGE_OCTAVO = (171.45, 260.35)


class Print:
    """A page plan: staff size, paper, margins, and where the systems begin.

    `systems` is the list of bar numbers that start a system.  Taking every
    `per_page`th of them gives the page breaks, so the two settings cannot
    disagree with each other.
    """

    def __init__(self, systems, staff_mm=7.0, page=PAGE_LETTER, per_page=2,
                 margins=None, system_distance=150, top_system_distance=90,
                 staff_distance=85, lyric_size=4.0, spacing_staff=4, spacing_system=20,
                 justify_vertically=False):
        self.systems = list(systems)
        self.staff_mm = staff_mm
        self.page_w, self.page_h = page
        self.per_page = per_page
        self.margins = margins or dict(left=14.0, right=11.0, top=13.0, bottom=12.0)
        self.system_distance = system_distance
        self.top_system_distance = top_system_distance
        self.staff_distance = staff_distance
        self.lyric_size = lyric_size
        self.spacing_staff = spacing_staff
        self.spacing_system = spacing_system
        self.justify_vertically = justify_vertically

    def tenths(self, mm):
        return round(mm / self.staff_mm * 40)

    def defaults_xml(self):
        mg = self.margins
        return ('<defaults>'
                f'<scaling><millimeters>{self.staff_mm}</millimeters><tenths>40</tenths></scaling>'
                f'<page-layout><page-height>{self.tenths(self.page_h)}</page-height>'
                f'<page-width>{self.tenths(self.page_w)}</page-width>'
                f'<page-margins type="both"><left-margin>{self.tenths(mg["left"])}</left-margin>'
                f'<right-margin>{self.tenths(mg["right"])}</right-margin>'
                f'<top-margin>{self.tenths(mg["top"])}</top-margin>'
                f'<bottom-margin>{self.tenths(mg["bottom"])}</bottom-margin></page-margins></page-layout>'
                '<system-layout><system-margins><left-margin>0</left-margin>'
                '<right-margin>0</right-margin></system-margins>'
                f'<system-distance>{self.system_distance}</system-distance>'
                f'<top-system-distance>{self.top_system_distance}</top-system-distance></system-layout>'
                f'<staff-layout><staff-distance>{self.staff_distance}</staff-distance></staff-layout>'
                '</defaults>')

    def lay_out(self, src):
        """Insert <defaults> and the encoded breaks. `src` is a path or XML text."""
        xml = src if src.lstrip().startswith('<') else open(src, encoding='utf-8').read()
        # <defaults> goes before <credit>, which goes before <part-list>; inserting
        # it straight before <part-list> puts it after any credits and fails the XSD.
        anchor = '<credit ' if '<credit ' in xml else '<part-list>'
        xml = xml.replace(anchor, self.defaults_xml() + anchor, 1)
        page_starts = {self.systems[i] for i in range(0, len(self.systems), self.per_page)}

        def ap(mo):
            m = int(mo.group(1))
            if m in page_starts and m != 1:
                return mo.group(0) + '<print new-page="yes"/>'
            if m in self.systems and m != 1:
                return mo.group(0) + '<print new-system="yes"/>'
            return mo.group(0)

        # MuseScore writes <measure number="1" width="253.75">; a pattern that
        # demands '>' right after the number silently inserts no breaks at all.
        return re.sub(r'<measure number="(\d+)"[^>]*>', ap, xml)

    def options(self):
        mg = self.margins
        return {"pageWidth": int(self.page_w * 10), "pageHeight": int(self.page_h * 10),
                "pageMarginLeft": int(mg['left'] * 10), "pageMarginRight": int(mg['right'] * 10),
                "pageMarginTop": int(mg['top'] * 10), "pageMarginBottom": int(mg['bottom'] * 10),
                "unit": self.staff_mm / 4 * 10 / 2, "scale": 100, "adjustPageHeight": False,
                "breaks": "encoded", "justifyVertically": self.justify_vertically,
                "spacingStaff": self.spacing_staff, "spacingSystem": self.spacing_system,
                "lyricSize": self.lyric_size, "svgViewBox": True,
                "header": "auto", "footer": "none"}

    def expand_credit_blocks(self, xml, leading=30):
        """Split a multi-line credit into one credit per line, for Verovio only.

        The two readers want opposite encodings, and a probe settles which:

        * Sibelius keeps ONE credit per zone of the page — given six separate
          credits aimed at the same corner it drew the last and silently
          dropped five — but renders every `<credit-words>` of a single credit
          as its own line.
        * Verovio is the mirror image: it draws every separate credit and only
          the first `<credit-words>` of a block.

        So the file keeps the block, which is what the notation program reads,
        and the renderer is handed the expansion. Nothing else sees this.
        """
        if xml.count('<credit-words') < 2:
            return xml
        from lxml import etree
        head, _, rest = xml.partition('<score-partwise')
        root = etree.fromstring(('<score-partwise' + rest).encode())
        for cr in root.findall('credit'):
            words = cr.findall('credit-words')
            if len(words) < 2:
                continue
            first = words[0]
            try:
                y0 = float(first.get('default-y'))
            except (TypeError, ValueError):
                continue
            idx = list(root).index(cr)
            for i, w in enumerate(words):
                one = etree.Element('credit')
                one.set('page', cr.get('page', '1'))
                cw = etree.SubElement(one, 'credit-words')
                for k, v in first.items():
                    cw.set(k, v)
                cw.set('default-y', f'{y0 - leading * i:g}')
                cw.text = (w.text or '').rstrip('\n')
                root.insert(idx + i, one)
            root.remove(cr)
        return head + etree.tostring(root, encoding='unicode')

    @staticmethod
    def close_extenders(xml):
        """End every lyric extender explicitly, for Verovio only.

        A plain `<extend/>` leaves the reader to infer where the line stops, and
        Verovio infers badly: it runs the line THROUGH rests to the next
        lyric-less note in the same voice, however far away.  On a shared staff
        voice 2 can vanish for bars at a time, so a melisma in one phrase grew a
        line that crossed three systems to reach an unrelated note seven bars
        later.  The fix is the spec's own: `<lyric><extend type="stop"/></lyric>`
        on the last note of each melisma — the last note before a rest, a new
        syllable on that line, or the end of the part.

        The file handed to a notation program keeps plain `<extend/>`, which is
        what MuseScore writes too; only the renderer sees this.
        """
        if '<extend' not in xml:
            return xml
        from lxml import etree
        head, _, rest = xml.partition('<score-partwise')
        root = etree.fromstring(('<score-partwise' + rest).encode())

        def stop(note, num):
            ly = etree.SubElement(note, 'lyric')
            ly.set('number', num)
            etree.SubElement(ly, 'extend').set('type', 'stop')

        for part in root.findall('part'):
            voices = {}
            for note in part.iter('note'):
                if note.find('chord') is not None:
                    continue
                voices.setdefault(note.findtext('voice') or '1', []).append(note)
            for notes in voices.values():
                open_ = {}                    # lyric number -> [start note, last note]
                for note in notes:
                    if note.find('rest') is not None:
                        for num, (a, b) in open_.items():
                            if b is not a:
                                stop(b, num)
                        open_.clear()
                        continue
                    sung = {ly.get('number', '1'): ly for ly in note.findall('lyric')
                            if ly.findtext('text')}
                    for num in list(open_):
                        if num in sung:
                            del open_[num]    # a new syllable ends the line by itself
                        else:
                            open_[num][1] = note
                    for num, ly in sung.items():
                        ext = ly.find('extend')
                        if ext is not None and ext.get('type') in (None, 'start'):
                            open_[num] = [note, note]
                for num, (a, b) in open_.items():
                    if b is not a:
                        stop(b, num)
        return head + etree.tostring(root, encoding='unicode')

    def toolkit(self, xml):
        import verovio
        tk = verovio.toolkit()
        tk.setOptions(self.options())
        tk.loadData(self.close_extenders(self.expand_credit_blocks(xml)))
        return tk

    def credit_xml(self, title, lines, title_size=22, size=10,
                   leading=30, gap=62, footer=None, footer_size=9,
                   footer_mm=6.5):
        """The <credit> elements, positioned in page coordinates.

        MusicXML page positions are in tenths, and the reference documentation
        is explicit that "the origin is changed relative to the bottom
        left-hand corner of the specified page", positive x right and positive
        y up. A credit with no default-x/default-y therefore defaults to (0, 0)
        — the bottom-left corner of the paper, flush to the edge — and several
        unpositioned credits land on top of one another there, so all but one
        look like they were dropped. Always give coordinates.

        Leave `kind` None unless you want the line swallowed. Sibelius takes a
        credit carrying a <credit-type> into its Score Info fields instead of
        drawing it on the page, so a typed composer line and a typed arranger
        line both vanish while an untyped one beside them prints. The names
        belong in <identification><creator> anyway; these are the copies meant
        to be seen. Verovio draws all of them, typed or not.
        """
        from .musicxml import credit
        page_w, page_h = self.tenths(self.page_w), self.tenths(self.page_h)
        right = page_w - self.tenths(self.margins['right'])
        top = page_h - self.tenths(self.margins['top'])
        out = []
        if title:
            out.append(credit(title, kind='title', justify='center',
                              valign='top', x=page_w // 2, y=top,
                              size=title_size))
        if lines:
            out.append(credit([t for _, t in lines], justify='right',
                              valign='top', x=right, y=top - gap, size=size))
        if footer:
            # Inside the bottom margin, not above it. Sibelius anchors the
            # copyright it generates from <rights> to the bottom margin and
            # then justifies the staves down onto that same line, so the two
            # collide and widening the margin moves both together — it cannot
            # separate them. A credit placed in the margin band clears the
            # music whatever the justification does. Drop <rights> from
            # <identification> when you use this, or you get both.
            out.append(credit(footer, justify='center', valign='bottom',
                              x=page_w // 2, y=self.tenths(footer_mm),
                              size=footer_size))
        return out

    def header_tenths(self, nlines, title_size=22, leading=30, gap=62):
        """How far the first system must sit below the top margin to clear the
        header block, so `system_distance` can be set from the credits rather
        than guessed at."""
        return int(gap + leading * nlines + title_size)

    def draw_footer(self, svg, text, mm=6.5, size=28):
        """Paint a footer line onto a rendered page.

        Verovio converts credits into its page *head* only: a credit
        positioned down in the bottom margin is dropped, and `footer` set to
        none, auto or encoded makes no difference — all three were tried. The
        notation program reads the credit from the file; the PDF needs the
        line drawn.
        """
        if not text:
            return svg
        from lxml import etree
        root = etree.fromstring(svg.encode())
        g = etree.SubElement(root, '{http://www.w3.org/2000/svg}g')
        g.set('class', 'footer')
        el = etree.SubElement(g, '{http://www.w3.org/2000/svg}text')
        el.set('x', f'{self.page_w * 10 / 2:.1f}')
        el.set('y', f'{self.page_h * 10 - mm * 10:.1f}')
        el.set('text-anchor', 'middle')
        el.set('font-family', 'Times,serif')
        el.set('font-size', f'{size}px')
        el.text = text
        return etree.tostring(root, encoding='unicode')

    def render(self, xml, pdf_out, png_pages=(), quiet=False, footer=None):
        """Write a print-ready PDF, and optionally PNGs of named pages."""
        import cairosvg
        tk = self.toolkit(xml)
        n = tk.getPageCount()
        svgs = [tk.renderToSVG(i) for i in range(1, n + 1)]
        if footer:
            svgs[0] = self.draw_footer(svgs[0], footer)
        per = [len(re.findall(r'class="system"', s)) for s in svgs]
        if not quiet:
            print(f'{n} pages, systems/page {per}')
        pdfs = [cairosvg.svg2pdf(bytestring=s.encode(), dpi=254) for s in svgs]
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            from PyPDF2 import PdfReader, PdfWriter
        w = PdfWriter()
        for b in pdfs:
            w.append(PdfReader(io.BytesIO(b)))
        with open(pdf_out, 'wb') as f:
            w.write(f)
        for p in png_pages:
            png_page(svgs[p - 1], f'{pdf_out[:-4]}_p{p}.png')
        return n, per


def png_page(svg, out, width=1500):
    """PNG of one rendered page, composited onto white.

    cairosvg writes a transparent background; measuring ink on the raw output
    counts the transparency as black and every page looks equally full.
    """
    import cairosvg
    from PIL import Image
    im = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(),
                                                output_width=width))).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    bg.convert('RGB').save(out)
    return out


def install_smufl_font(force=False):
    """Make Verovio's Leipzig visible to cairosvg, killing the tofu rectangles.

    Verovio ships the font base64'd inside data/Leipzig.css as WOFF2; fontconfig
    cannot read WOFF2, so it is converted on the way out.  Returns the installed
    path, or None if the font was already there.
    """
    import verovio
    dest_dir = os.path.expanduser('~/.fonts')
    dest = os.path.join(dest_dir, 'Leipzig.ttf')
    if os.path.exists(dest) and not force:
        return None
    css_path = os.path.join(os.path.dirname(verovio.__file__), 'data', 'Leipzig.css')
    css = open(css_path, encoding='utf-8').read()
    m = re.search(r'base64,([A-Za-z0-9+/=]+)', css)
    if not m:
        raise RuntimeError(f'no embedded font found in {css_path}')
    raw = base64.b64decode(m.group(1))
    from fontTools.ttLib import TTFont
    f = TTFont(io.BytesIO(raw))
    f.flavor = None
    os.makedirs(dest_dir, exist_ok=True)
    f.save(dest)
    subprocess.run(['fc-cache', '-f'], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest
