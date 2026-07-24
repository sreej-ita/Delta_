from fpdf import FPDF
from datetime import datetime
import io


def _pdf_safe(text):
    """
    Strips/replaces characters unsupported by FPDF's default Latin-1 fonts
    (e.g. em dashes, curly quotes) so report generation never crashes on
    dynamic content (project names, notes, etc.).
    """
    if text is None:
        return ""
    text = str(text)
    replacements = {
        '\u2014': '-', '\u2013': '-',   # em dash, en dash
        '\u2018': "'", '\u2019': "'",   # curly single quotes
        '\u201c': '"', '\u201d': '"',   # curly double quotes
        '\u2026': '...',                # ellipsis
    }
    for uni_char, ascii_char in replacements.items():
        text = text.replace(uni_char, ascii_char)
    return text.encode('latin-1', errors='replace').decode('latin-1')


class EcosystemReport(FPDF):
    def header(self):
        # Skip header on the title page (page 1)
        if self.page_no() == 1:
            return
        self.set_font('Helvetica', 'B', 13)
        self.set_text_color(16, 130, 80)
        self.cell(0, 8, _pdf_safe('Blue Carbon MRV Evidence Pack'), border=0, ln=1, align='L')

        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, _pdf_safe('Indicative Remote-Sensing Monitoring Summary'), border=0, ln=1, align='L')

        self.set_draw_color(16, 130, 80)
        self.set_line_width(0.4)
        self.line(10, 20, 200, 20)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(
            0, 10,
            _pdf_safe(f'Page {self.page_no()}/{{nb}}  |  Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}  |  Indicative document, not a formal verification'),
            border=0, align='C'
        )

    def section_title(self, text):
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(30, 41, 59)
        self.cell(0, 8, _pdf_safe(text), ln=1)

    def kv_row(self, label, value, label_w=55, value_w=135):
        self.set_font('Helvetica', 'B', 9)
        self.set_fill_color(248, 250, 252)
        self.cell(label_w, 6, _pdf_safe(f'  {label}'), border=1, fill=True)
        self.set_font('Helvetica', '', 9)
        self.cell(value_w, 6, _pdf_safe(f' {value}'), border=1, ln=1)


def generate_pdf_report(project_name, analysis_data, carbon_data, project_meta=None, checklist=None):
    """
    Generates a structured, audit-ready PDF evidence pack:
      1. Title page
      2. Project summary
      3. Monitoring period
      4. Key metrics
      5. Checklist findings (pre-verification)
      6. Limitations
      7. Appendix (carbon pool table, deforestation alert log)

    This is explicitly an INDICATIVE document, not a certified verification —
    wording throughout avoids implying formal approval or guaranteed credits.

    Returns:
        bytes: Raw PDF file bytes to be served in a Streamlit download button.
    """
    if project_meta is None:
        project_meta = {}
    if checklist is None:
        checklist = []

    pdf = EcosystemReport()
    pdf.alias_nb_pages()

    # ======================================================
    # PAGE 1: TITLE PAGE
    # ======================================================
    pdf.add_page()
    pdf.ln(30)

    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(16, 130, 80)
    pdf.multi_cell(0, 12, _pdf_safe('Blue Carbon MRV Evidence Pack'), align='C')
    pdf.ln(2)

    pdf.set_font('Helvetica', 'I', 13)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(0, 8, _pdf_safe('Indicative Pre-Verification Monitoring Summary'), align='C')
    pdf.ln(15)

    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(0, 8, _pdf_safe(project_name), align='C')
    pdf.ln(4)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 6, _pdf_safe(analysis_data.get('location_name', 'Location unavailable')), align='C')
    pdf.ln(20)

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(130, 130, 130)
    pdf.multi_cell(0, 5, _pdf_safe(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), align='C')
    pdf.ln(30)

    pdf.set_draw_color(16, 130, 80)
    pdf.set_fill_color(240, 253, 244)
    pdf.rect(20, pdf.get_y(), 170, 20, style='DF')
    pdf.set_y(pdf.get_y() + 3)
    pdf.set_font('Helvetica', 'B', 8.5)
    pdf.set_text_color(22, 101, 52)
    pdf.multi_cell(
        160, 4,
        _pdf_safe(
            'This is an indicative, remote-sensing-based pre-verification assessment. It is not a '
            'certified or approved verification. Formal carbon credit verification requires review '
            'by an accredited verification body under an established methodology.'
        ),
        align='C'
    )

    # ======================================================
    # PAGE 2: PROJECT SUMMARY
    # ======================================================
    pdf.add_page()
    pdf.section_title('1. Project Summary')

    metadata = [
        ('Project Identifier:', project_name),
        ('Region Name:', analysis_data.get('location_name', 'Unknown')),
        ('Project Area:', f"{analysis_data.get('area_ha', 0)} hectares (ha)"),
        ('Analysis Boundary:', 'Polygon defined via administrative reference or user-drawn area'),
        ('Boundary Confidence:', project_meta.get('data_confidence', 'unverified').capitalize()),
    ]
    if project_meta:
        metadata.extend([
            ('Registry Standard (stated):', project_meta.get('standard', 'N/A')),
            ('Trees Planted (stated):', project_meta.get('trees', 'N/A')),
            ('Species Composition:', project_meta.get('species', 'N/A')),
        ])

    for label, val in metadata:
        pdf.kv_row(label, val)

    pdf.ln(6)

    # ======================================================
    # SECTION 2: MONITORING PERIOD
    # ======================================================
    pdf.section_title('2. Monitoring Period')

    trend = analysis_data.get('real_5yr_ndvi_trend')
    if trend:
        years = [str(t['year']) for t in trend]
        pdf.kv_row('Baseline period:', f"{years[0]} - {years[-1]} ({len(trend)} year(s) of real Sentinel-2 data)")
    else:
        pdf.kv_row('Baseline period:', 'Real baseline data not available for this session')

    pdf.kv_row('Current monitoring window:', 'Most recent available satellite pass (last ~9 months)')

    data_state = 'Live satellite data' if not analysis_data.get('is_cached') else 'Most recent cached real result (live fetch unavailable this session)'
    pdf.kv_row('Data currency:', data_state)

    pdf.ln(6)

    # ======================================================
    # SECTION 3: KEY METRICS
    # ======================================================
    pdf.section_title('3. Key Metrics')

    pdf.set_fill_color(240, 253, 244)
    pdf.set_draw_color(187, 247, 208)
    pdf.rect(10, pdf.get_y(), 190, 16, style='DF')

    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(22, 101, 52)
    pdf.cell(0, 8, _pdf_safe(f'  Indicative Carbon Estimate (CO2 Equivalent): {carbon_data.get("total_co2e_tons", 0):,} tCO2e'), ln=1)
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, _pdf_safe(f'  Density: {carbon_data.get("co2e_per_ha", 0):,} tCO2e/ha  |  Est. Annual Sequestration: {carbon_data.get("annual_sequestration_tco2e", 0):,} tCO2e/yr'), ln=1)
    pdf.ln(6)

    biomass_source = carbon_data.get('data_source', 'unknown')
    biomass_source_label = {
        'gedi_measured': 'Real GEDI L4A satellite-measured biomass',
        'model_real_trained': 'ML model trained on real GEDI + Sentinel-2 data (no GEDI footprint in this area)',
        'model_synthetic_fallback': 'Fallback model trained on synthetic data (no GEDI footprint in this area)'
    }.get(biomass_source, 'Unknown')
    pdf.kv_row('Biomass data source:', biomass_source_label)

    pdf.set_text_color(30, 41, 59)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(226, 232, 240)
    pdf.cell(75, 6, _pdf_safe('Index / Sensor metric'), border=1, fill=True)
    pdf.cell(25, 6, _pdf_safe('Current Value'), border=1, fill=True)
    pdf.cell(90, 6, _pdf_safe('Interpretation'), border=1, ln=1, fill=True)

    indices = [
        ('NDVI (Vegetation Index)', f"{analysis_data.get('current_ndvi', 0):.3f}", 'Healthy mangrove canopy typically 0.65-0.85.'),
        ('NDWI (Water Index)', f"{analysis_data.get('current_ndwi', 0):.3f}", 'Waterlogged wetland typically 0.20-0.50.'),
        ('ET Stress Index', f"{analysis_data.get('current_et_stress', 0):.2f}", '0.00 (unstressed) to 1.00 (severe moisture deficit).'),
    ]
    pdf.set_font('Helvetica', '', 9)
    for label, val, desc in indices:
        pdf.cell(75, 6, _pdf_safe(f' {label}'), border=1)
        pdf.cell(25, 6, _pdf_safe(f' {val}'), border=1, align='C')
        pdf.cell(90, 6, _pdf_safe(f' {desc}'), border=1, ln=1)

    pdf.ln(6)

    # ======================================================
    # SECTION 4: CHECKLIST FINDINGS
    # ======================================================
    pdf.add_page()
    pdf.section_title('4. Pre-Verification Checklist Findings')

    pdf.set_font('Helvetica', 'I', 8.5)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, _pdf_safe(
        'Each item below is derived directly from the monitoring evidence collected for this '
        'project. This checklist supports, but does not replace, formal verification.'
    ))
    pdf.ln(3)

    status_symbol = {'pass': '[OK]', 'warning': '[REVIEW]', 'fail': '[GAP]'}
    status_color = {'pass': (22, 101, 52), 'warning': (161, 98, 7), 'fail': (153, 27, 27)}

    if checklist:
        for entry in checklist:
            status = entry.get('status', 'warning')
            symbol = status_symbol.get(status, '[REVIEW]')
            color = status_color.get(status, (100, 100, 100))

            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*color)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, _pdf_safe(f"{symbol} {entry.get('item', '')}"))

            pdf.set_font('Helvetica', '', 8.5)
            pdf.set_text_color(90, 90, 90)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 4.5, _pdf_safe(f"    {entry.get('note', '')}"))
            pdf.ln(1.5)
    else:
        pdf.set_font('Helvetica', 'I', 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 6, _pdf_safe('No checklist data was provided for this report.'), ln=1)

    pdf.set_text_color(30, 41, 59)
    pdf.ln(4)

    # ======================================================
    # SECTION 5: LIMITATIONS
    # ======================================================
    pdf.section_title('5. Limitations')

    pdf.set_font('Helvetica', '', 8.5)
    pdf.set_text_color(60, 60, 60)
    limitations = [
        'This document provides an indicative carbon estimate derived from public remote-sensing '
        'datasets (Sentinel-2, MODIS, SRTM, GEDI) and methodology-aligned models. It is not a '
        'certified or approved carbon credit verification.',
        'Formal verification requires review by an accredited verification body under an established '
        'methodology (e.g. VCS, Gold Standard). This report does not guarantee issuance of carbon credits.',
        'Where real GEDI biomass measurement is unavailable for a given area (sparse satellite '
        'footprint coverage), biomass is estimated using a documented allometric model instead; this '
        'is flagged explicitly in Section 3 and the checklist above.',
        'Optical satellite indices (NDVI/NDWI) can be affected by cloud cover, seasonal variation, and '
        'tidal conditions; the most recent usable clear-sky composite is used where available.',
    ]
    for line in limitations:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 4.5, _pdf_safe(f'- {line}'))
        pdf.ln(1)

    pdf.ln(4)

    # ======================================================
    # APPENDIX: CARBON POOL TABLE + DEFORESTATION LOG
    # ======================================================
    pdf.add_page()
    pdf.section_title('Appendix A: Carbon Pool Breakdown')

    agc = carbon_data.get('aboveground_carbon_tc', 0)
    bgc = carbon_data.get('belowground_carbon_tc', 0)
    soc = carbon_data.get('soil_organic_carbon_tc', 0)
    tot = carbon_data.get('total_carbon_tc', 1) or 1

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(226, 232, 240)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(70, 6, _pdf_safe('Carbon Reservoir Pool'), border=1, fill=True)
    pdf.cell(60, 6, _pdf_safe('Estimated Carbon (tC)'), border=1, fill=True)
    pdf.cell(60, 6, _pdf_safe('Percentage of Total (%)'), border=1, ln=1, fill=True)

    pools = [
        ('Aboveground Biomass', agc, (agc / tot) * 100),
        ('Belowground Biomass (Roots)', bgc, (bgc / tot) * 100),
        ('Soil Organic Carbon (0-1m)', soc, (soc / tot) * 100),
    ]
    pdf.set_font('Helvetica', '', 9)
    for name, tc, pct in pools:
        pdf.cell(70, 6, _pdf_safe(f' {name}'), border=1)
        pdf.cell(60, 6, _pdf_safe(f' {tc:,.1f} tC'), border=1)
        pdf.cell(60, 6, _pdf_safe(f' {pct:.1f} %'), border=1, ln=1)

    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(70, 6, _pdf_safe(' Combined Total'), border=1)
    pdf.cell(60, 6, _pdf_safe(f' {tot:,.1f} tC'), border=1)
    pdf.cell(60, 6, _pdf_safe(' 100.0 %'), border=1, ln=1)

    pdf.ln(8)

    pdf.section_title('Appendix B: Deforestation / Canopy-Loss Alert Log')

    detection_method = analysis_data.get('deforestation_detection_method', 'simulated')
    method_label = 'Real Sentinel-2 NDVI change detection' if detection_method == 'real' else 'Simulated (real detection unavailable this session)'
    pdf.kv_row('Detection method:', method_label)

    alerts = analysis_data.get('deforestation_alerts', [])

    if not alerts:
        pdf.set_font('Helvetica', 'I', 9.5)
        pdf.set_text_color(16, 120, 70)
        pdf.cell(0, 6, _pdf_safe('  No canopy loss or deforestation alerts detected in this area over the monitoring period.'), ln=1)
        pdf.set_text_color(30, 41, 59)
    else:
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(254, 226, 226)
        pdf.set_text_color(153, 27, 27)
        pdf.cell(30, 6, _pdf_safe('Date'), border=1, fill=True)
        pdf.cell(60, 6, _pdf_safe('GPS Coordinate (Lat, Lng)'), border=1, fill=True)
        pdf.cell(50, 6, _pdf_safe('Estimated Loss'), border=1, fill=True)
        pdf.cell(50, 6, _pdf_safe('Severity'), border=1, ln=1, fill=True)

        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(30, 41, 59)
        for alt in alerts[:5]:
            pdf.cell(30, 6, _pdf_safe(f' {alt.get("date")}'), border=1)
            pdf.cell(60, 6, _pdf_safe(f' {alt.get("latitude")}, {alt.get("longitude")}'), border=1)
            pdf.cell(50, 6, _pdf_safe(f' {alt.get("area_loss_sqm"):,.1f} sqm'), border=1)
            pdf.cell(50, 6, _pdf_safe(f' {alt.get("severity")}'), border=1, ln=1)

        if len(alerts) > 5:
            pdf.set_font('Helvetica', 'I', 8)
            pdf.cell(0, 6, _pdf_safe(f'  Note: {len(alerts) - 5} additional alert(s) omitted from this appendix. See live portal for full log.'), ln=1)

    # Output PDF stream
    pdf_buffer = io.BytesIO()
    pdf_out = pdf.output(dest='S')
    if isinstance(pdf_out, str):
        pdf_buffer.write(pdf_out.encode('latin1'))
    else:
        pdf_buffer.write(pdf_out)

    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()