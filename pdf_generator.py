import os
import io
import json
from datetime import datetime
from PIL import Image

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
    KeepTogether, PageBreak, HRFlowable
)
from reportlab.pdfgen import canvas

# Color Palette
COLOR_PRIMARY = colors.HexColor('#121212')      # Obsidian Charcoal
COLOR_SECONDARY = colors.HexColor('#4A4A4A')    # Slate Grey
COLOR_ACCENT = colors.HexColor('#8C7355')       # Warm Architectural Bronze
COLOR_BG_LIGHT = colors.HexColor('#F8F7F4')     # Warm Off-White
COLOR_BORDER = colors.HexColor('#E5E3DC')       # Structural Border
COLOR_MUTED = colors.HexColor('#737373')        # Muted Text

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            return  # Skip header and footer on cover page

        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_MUTED)

        # Running Header
        self.drawString(54, 800, "SHAMEER ASSOCIATES  •  RESIDENTIAL DESIGN BRIEF")
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.5)
        self.line(54, 792, 541, 792)

        # Running Footer
        self.line(54, 45, 541, 45)
        self.drawString(54, 32, "Confidential Architectural Client Brief")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(541, 32, page_text)
        self.restoreState()


def get_custom_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='CoverBrand',
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=COLOR_PRIMARY,
        alignment=1, # Center
        spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        name='CoverTagline',
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=COLOR_ACCENT,
        alignment=1,
        spaceAfter=15
    ))
    styles.add(ParagraphStyle(
        name='CoverMotto',
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=COLOR_PRIMARY,
        alignment=1,
        spaceAfter=25
    ))
    styles.add(ParagraphStyle(
        name='CoverDocTitle',
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=COLOR_PRIMARY,
        alignment=1,
        spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name='CoverMeta',
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=COLOR_SECONDARY,
        alignment=1
    ))
    styles.add(ParagraphStyle(
        name='ChapterHeading',
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=COLOR_PRIMARY,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    ))
    styles.add(ParagraphStyle(
        name='SectionHeading',
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=COLOR_ACCENT,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    ))
    styles.add(ParagraphStyle(
        name='QuestionLabel',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=COLOR_PRIMARY
    ))
    styles.add(ParagraphStyle(
        name='AnswerValue',
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=COLOR_SECONDARY
    ))
    styles.add(ParagraphStyle(
        name='PhilosophyBoxTitle',
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        textColor=COLOR_PRIMARY,
        spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        name='PhilosophyBoxText',
        fontName='Helvetica',
        fontSize=8,
        leading=10.5,
        textColor=COLOR_SECONDARY
    ))
    styles.add(ParagraphStyle(
        name='VisualStyleTitle',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=COLOR_PRIMARY,
        spaceAfter=2
    ))
    styles.add(ParagraphStyle(
        name='VisualDesc',
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=10.5,
        textColor=COLOR_SECONDARY
    ))
    return styles


def format_val(val):
    if val is None or val == "":
        return "—"
    if isinstance(val, list):
        if len(val) == 0:
            return "—"
        return ", ".join(str(item) for item in val)
    if isinstance(val, bool):
        return "Yes" if val else "No"
    return str(val)


def create_qa_table(qa_pairs, styles, col_widths=[190, 297]):
    table_data = []
    for label, val in qa_pairs:
        p_label = Paragraph(f"<b>{label}</b>", styles['QuestionLabel'])
        p_val = Paragraph(format_val(val), styles['AnswerValue'])
        table_data.append([p_label, p_val])

    if not table_data:
        return None

    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('BACKGROUND', (0, 0), (0, -1), COLOR_BG_LIGHT)
    ]))
    return t


def generate_pdf_bytes(session_data, schema):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = get_custom_styles()
    story = []

    answers = session_data.get('answers', {})
    family_members = session_data.get('family_members', [])
    dynamic_rooms = session_data.get('dynamic_rooms', [])
    selected_visuals = session_data.get('selected_visuals', {})
    client_name = answers.get('client_name', 'Client') or 'Client'
    location = answers.get('project_location', 'Kerala, India') or 'Kerala, India'
    date_str = datetime.now().strftime('%d %B %Y')

    # =========================================================
    # 1. COVER PAGE
    # =========================================================
    story.append(Spacer(1, 20))

    # Logo
    logo_path = 'static/brand/shameer_associates_logo.png'
    if os.path.exists(logo_path):
        story.append(RLImage(logo_path, width=110, height=110))
        story.append(Spacer(1, 15))

    story.append(Paragraph("SHAMEER ASSOCIATES", styles['CoverBrand']))
    story.append(Paragraph("ARCHITECTURE • INTERIORS • LANDSCAPE", styles['CoverTagline']))
    story.append(HRFlowable(width="30%", thickness=1.5, color=COLOR_ACCENT, spaceAfter=20, spaceBefore=5))
    
    story.append(Paragraph("YOUR HOME. YOUR STORY. YOUR DESIGN.", styles['CoverMotto']))
    story.append(Paragraph("RESIDENTIAL DESIGN BRIEF", styles['CoverDocTitle']))
    story.append(Spacer(1, 10))

    meta_text = f"<b>Client:</b> {client_name}<br/><b>Project Location:</b> {location}<br/><b>Date:</b> {date_str}"
    story.append(Paragraph(meta_text, styles['CoverMeta']))
    story.append(Spacer(1, 35))

    # ICREATE Values Box on Cover
    icreate_data = [
        [Paragraph("<b>ICREATE STUDIO PHILOSOPHY</b>", styles['PhilosophyBoxTitle'])],
        [Paragraph(
            "<b>I</b>ntegrity in our commitments  •  <b>C</b>reativity in every design solution  •  "
            "<b>R</b>elationships built through listening  •  <b>E</b>xcellence in quality  •  "
            "<b>A</b>ttention to Detail  •  <b>T</b>imeliness  •  <b>E</b>volution through innovation.<br/><br/>"
            "<i>\"Our vision is to create emotionally intelligent, climate-responsive and fully integrated homes for conscious families—not merely houses designed to impress, but meaningful homes created to belong.\"</i>",
            styles['PhilosophyBoxText']
        )]
    ]
    t_icreate = Table(icreate_data, colWidths=[487])
    t_icreate.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, COLOR_ACCENT),
        ('PADDING', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    story.append(t_icreate)
    story.append(PageBreak())

    # =========================================================
    # 2. CHAPTER 1: PROJECT FOUNDATION & FAMILY LIFE
    # =========================================================
    story.append(Paragraph("01. PROJECT FOUNDATION & FAMILY LIFE", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))

    # 1.1 Contact & Site
    story.append(Paragraph("1.1 Contact & Site Information", styles['SectionHeading']))
    site_qa = [
        ("Client Name", answers.get('client_name')),
        ("Contact / WhatsApp", answers.get('contact_number')),
        ("Email Address", answers.get('email_address')),
        ("Alternative Contact", answers.get('alt_contact')),
        ("Project Location / Address", answers.get('project_location')),
        ("Plot Size & Dimensions", answers.get('plot_size')),
        ("Road vs Plot Level", answers.get('road_vs_plot_level')),
        ("Site Condition", answers.get('site_condition')),
        ("Existing Structures", answers.get('existing_structures')),
        ("Existing Structure Details", answers.get('existing_structure_desc')),
        ("Site Survey / Levels Drawing", answers.get('site_survey_available'))
    ]
    t_site = create_qa_table([q for q in site_qa if q[1] is not None and q[1] != ""], styles)
    if t_site:
        story.append(t_site)
        story.append(Spacer(1, 8))

    # 1.2 Project Overview
    story.append(Paragraph("1.2 Project Overview", styles['SectionHeading']))
    overview_qa = [
        ("Project Type", answers.get('project_type')),
        ("Number of Floors", answers.get('number_of_floors')),
        ("Expected Built-up Area (sq. ft.)", answers.get('expected_builtup_area')),
        ("Future Floor Expansion Planned", answers.get('future_expansion')),
        ("Expected Project Start", answers.get('expected_start')),
        ("Desired Completion Timeline", answers.get('desired_timeline'))
    ]
    t_overview = create_qa_table([q for q in overview_qa if q[1] is not None and q[1] != ""], styles)
    if t_overview:
        story.append(t_overview)
        story.append(Spacer(1, 8))

    # 1.3 Family & Household Composition
    story.append(Paragraph("1.3 Family & Household Composition", styles['SectionHeading']))
    story.append(Paragraph(f"<b>Total Household Members:</b> {format_val(answers.get('total_people'))}", styles['AnswerValue']))
    story.append(Spacer(1, 4))

    if family_members:
        fam_table_data = [
            [
                Paragraph("<b>User Group</b>", styles['QuestionLabel']),
                Paragraph("<b>Count</b>", styles['QuestionLabel']),
                Paragraph("<b>Gender</b>", styles['QuestionLabel']),
                Paragraph("<b>Age Range</b>", styles['QuestionLabel']),
                Paragraph("<b>Special Notes</b>", styles['QuestionLabel'])
            ]
        ]
        for fm in family_members:
            fam_table_data.append([
                Paragraph(fm.get('user_group', ''), styles['AnswerValue']),
                Paragraph(str(fm.get('count', 1)), styles['AnswerValue']),
                Paragraph(fm.get('gender', '—'), styles['AnswerValue']),
                Paragraph(fm.get('age_range', '—'), styles['AnswerValue']),
                Paragraph(fm.get('special_note', '—'), styles['AnswerValue'])
            ])
        t_fam = Table(fam_table_data, colWidths=[100, 45, 70, 80, 192])
        t_fam.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_LIGHT),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        story.append(t_fam)
        story.append(Spacer(1, 6))

    fam_qa = [
        ("Accessibility / Safety Requirements", answers.get('accessibility_requirements')),
        ("Frequent Guests / Visiting Family", answers.get('frequent_guests')),
        ("Live-in Staff / Caretaker", answers.get('live_in_staff'))
    ]
    t_fam_qa = create_qa_table([q for q in fam_qa if q[1] is not None and q[1] != ""], styles)
    if t_fam_qa:
        story.append(t_fam_qa)
        story.append(Spacer(1, 8))

    # 1.4 Lifestyle & Daily Habits
    story.append(Paragraph("1.4 Lifestyle & Daily Habits", styles['SectionHeading']))
    lifestyle_qa = [
        ("Living Style Preference", answers.get('living_style')),
        ("Daily Pace at Home", answers.get('daily_pace')),
        ("Home Atmosphere Loved", answers.get('home_atmosphere')),
        ("Main Priorities for Home", answers.get('main_priorities')),
        ("Work From Home", answers.get('work_from_home')),
        ("WFH Space Needs", answers.get('wfh_needs_desc')),
        ("Prayer / Religious Practices", answers.get('prayer_practices')),
        ("Outdoor Habits", answers.get('outdoor_habits')),
        ("Entertainment Pattern", answers.get('entertainment_pattern')),
        ("Hobbies Requiring Dedicated Space", answers.get('hobbies_dedicated_space'))
    ]
    t_lifestyle = create_qa_table([q for q in lifestyle_qa if q[1] is not None and q[1] != ""], styles)
    if t_lifestyle:
        story.append(t_lifestyle)
        story.append(Spacer(1, 8))

    # 1.5 Decision-Making & 1.6 Budget
    story.append(Paragraph("1.5 Decision-Making & Communication", styles['SectionHeading']))
    decision_qa = [
        ("Decision-Making Style", answers.get('decision_making_style')),
        ("Final Approval for Design Changes", answers.get('final_approval')),
        ("Final Say in Case of Difference", answers.get('final_say_differ')),
        ("Preferred Communication Channel", answers.get('preferred_comm_method')),
        ("Meeting Frequency", answers.get('meeting_frequency')),
        ("Involvement Level", answers.get('involvement_level')),
        ("Open to Suggestions", answers.get('open_to_suggestions'))
    ]
    t_dec = create_qa_table([q for q in decision_qa if q[1] is not None and q[1] != ""], styles)
    if t_dec:
        story.append(t_dec)
        story.append(Spacer(1, 8))

    story.append(Paragraph("1.6 Budget & Services Required", styles['SectionHeading']))
    budget_qa = [
        ("Approximate Total Budget", answers.get('total_budget')),
        ("Budget Flexibility", answers.get('budget_flexibility')),
        ("Overall Quality Level", answers.get('quality_level')),
        ("Top Priority in Project", answers.get('top_priority')),
        ("Services Required from Shameer Associates", answers.get('services_required')),
        ("Contractor Status", answers.get('contractor_status'))
    ]
    t_budget = create_qa_table([q for q in budget_qa if q[1] is not None and q[1] != ""], styles)
    if t_budget:
        story.append(t_budget)
        story.append(Spacer(1, 10))

    # =========================================================
    # 3. CHAPTER 2: CLIMATE, LIGHT, VENTILATION & EXTERIOR
    # =========================================================
    story.append(PageBreak())
    story.append(Paragraph("02. CLIMATE, LIGHT, VENTILATION & ZONING", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))

    story.append(Paragraph("2.1 Climate, Light & Ventilation", styles['SectionHeading']))
    climate_qa = [
        ("Importance of Natural Light", answers.get('natural_light_importance')),
        ("Skylights Required", answers.get('skylights_required')),
        ("Skylight Type", answers.get('skylight_type')),
        ("Importance of Natural Ventilation", answers.get('natural_ventilation_importance')),
        ("Vastu Requirements", answers.get('vastu_requirements')),
        ("Preferred Cooling Strategy", answers.get('cooling_strategy')),
        ("Passive Cooling Features", answers.get('passive_cooling_features')),
        ("Window Strategy Preference", answers.get('window_strategy'))
    ]
    t_climate = create_qa_table([q for q in climate_qa if q[1] is not None and q[1] != ""], styles)
    if t_climate:
        story.append(t_climate)
        story.append(Spacer(1, 8))

    story.append(Paragraph("2.2 Space Zoning & Privacy", styles['SectionHeading']))
    zoning_qa = [
        ("Zone Separation Preference", answers.get('zone_separation')),
        ("Privacy Level Overall", answers.get('overall_privacy')),
        ("Kitchen Visibility from Guest Areas", answers.get('kitchen_visibility_guest'))
    ]
    t_zoning = create_qa_table([q for q in zoning_qa if q[1] is not None and q[1] != ""], styles)
    if t_zoning:
        story.append(t_zoning)
        story.append(Spacer(1, 8))

    # Exterior Style Visual Reference
    story.append(Paragraph("2.3 Selected Exterior Architectural Style", styles['SectionHeading']))
    ext_vis = selected_visuals.get('exterior')
    if ext_vis:
        img_rel = ext_vis.get('image_url', '').lstrip('/')
        if os.path.exists(img_rel):
            ext_table_data = [
                [
                    RLImage(img_rel, width=220, height=130),
                    [
                        Paragraph(f"<b>Style {ext_vis.get('style_number', '')}: {ext_vis.get('style_name', '')}</b>", styles['VisualStyleTitle']),
                        Spacer(1, 4),
                        Paragraph(answers.get('exterior_notes', 'Client selected visual reference for exterior elevation direction.'), styles['VisualDesc'])
                    ]
                ]
            ]
            t_ext_vis = Table(ext_table_data, colWidths=[230, 257])
            t_ext_vis.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER)
            ]))
            story.append(t_ext_vis)
            story.append(Spacer(1, 10))
    else:
        story.append(Paragraph(f"<b>Exterior Notes:</b> {format_val(answers.get('exterior_notes'))}", styles['AnswerValue']))
        story.append(Spacer(1, 8))

    # =========================================================
    # 4. CHAPTER 3: SOCIAL & PUBLIC SPACES
    # =========================================================
    story.append(PageBreak())
    story.append(Paragraph("03. SOCIAL & PUBLIC SPACES", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))

    # Car Porch & Sitout
    story.append(Paragraph("3.1 Car Porch & 3.2 Sit-out", styles['SectionHeading']))
    porch_qa = [
        ("Vehicle Accommodation", answers.get('porch_vehicles')),
        ("Porch Structure Type", answers.get('porch_structure')),
        ("Additional Porch Features", answers.get('porch_features')),
        ("Sit-out Required", answers.get('sitout_required')),
        ("Sit-out Primary Use", answers.get('sitout_primary_use')),
        ("Sit-out Shape", answers.get('sitout_shape'))
    ]
    t_porch = create_qa_table([q for q in porch_qa if q[1] is not None and q[1] != ""], styles)
    if t_porch:
        story.append(t_porch)
        story.append(Spacer(1, 8))

    # Formal Living & Dining
    story.append(Paragraph("3.3 Formal Living & 3.4 Dining Room", styles['SectionHeading']))
    living_dining_qa = [
        ("Formal Living Arrangement", answers.get('formal_living_arrangement')),
        ("Formal Living Purpose", answers.get('formal_living_purpose')),
        ("Formal Living Seating Capacity", answers.get('formal_living_seating')),
        ("Dining Arrangement", answers.get('dining_arrangement')),
        ("Dining Usage Pattern", answers.get('dining_usage')),
        ("Dining Seating Capacity", answers.get('dining_seating_capacity')),
        ("Dining Preferred Connections", answers.get('dining_connections')),
        ("Additional Dining Furniture", answers.get('dining_furniture'))
    ]
    t_liv_din = create_qa_table([q for q in living_dining_qa if q[1] is not None and q[1] != ""], styles)
    if t_liv_din:
        story.append(t_liv_din)
        story.append(Spacer(1, 8))

    # Selected Formal Living & Dining Reference
    fld_vis = selected_visuals.get('formal_living_dining')
    if fld_vis:
        story.append(Paragraph("Selected Formal Living & Dining Design Reference", styles['SectionHeading']))
        liv_img_rel = fld_vis.get('living_image_url', '').lstrip('/')
        din_img_rel = fld_vis.get('dining_image_url', '').lstrip('/')
        
        fld_imgs = []
        if os.path.exists(liv_img_rel):
            fld_imgs.append(RLImage(liv_img_rel, width=150, height=95))
        if os.path.exists(din_img_rel):
            fld_imgs.append(RLImage(din_img_rel, width=150, height=95))

        fld_table_data = [
            [
                fld_imgs[0] if len(fld_imgs) > 0 else "",
                fld_imgs[1] if len(fld_imgs) > 1 else "",
                [
                    Paragraph(f"<b>Style {fld_vis.get('style_number', '')}: {fld_vis.get('style_name', '')}</b>", styles['VisualStyleTitle']),
                    Spacer(1, 3),
                    Paragraph("Formal Living & Dining Paired Reference", styles['VisualDesc'])
                ]
            ]
        ]
        t_fld_vis = Table(fld_table_data, colWidths=[155, 155, 177])
        t_fld_vis.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER)
        ]))
        story.append(t_fld_vis)
        story.append(Spacer(1, 10))

    # Family Living, Upper Lounge & Staircase
    story.append(Paragraph("3.5 Family Living, 3.6 Upper Lounge & 3.7 Staircase", styles['SectionHeading']))
    fam_liv_qa = [
        ("Family Living Arrangement", answers.get('family_living_arrangement')),
        ("Family Living Seating", answers.get('family_living_seating')),
        ("Family Living Mood / Feeling", answers.get('family_living_mood')),
        ("Family Living Additional Elements", answers.get('family_living_elements')),
        ("Upper Living Required", answers.get('upper_living_required')),
        ("Upper Living Primary Use", answers.get('upper_living_use')),
        ("Staircase Location Preference", answers.get('staircase_location')),
        ("Staircase Configuration", answers.get('staircase_configuration')),
        ("Staircase Materials", answers.get('staircase_fabrication')),
        ("Staircase Design Intent", answers.get('staircase_design_intent'))
    ]
    t_fam_liv = create_qa_table([q for q in fam_liv_qa if q[1] is not None and q[1] != ""], styles)
    if t_fam_liv:
        story.append(t_fam_liv)
        story.append(Spacer(1, 8))

    # Home Theatre, Powder Room, Wudu & Prayer Room
    story.append(Paragraph("3.8 Home Theatre, 3.9 Powder Room, 3.10 Ablution & 3.11 Prayer Room", styles['SectionHeading']))
    ht_prayer_qa = [
        ("Home Theatre Required", answers.get('home_theatre_required')),
        ("Home Theatre Mood & Seating", [format_val(answers.get('ht_mood')), format_val(answers.get('ht_seating_preference'))]),
        ("Powder Room Design Character", answers.get('powder_design_character')),
        ("Ablution / Wudu Location", answers.get('wudu_location')),
        ("Prayer Space Type", answers.get('prayer_space_type')),
        ("Prayer Room Character & Feeling", [format_val(answers.get('prayer_character')), format_val(answers.get('prayer_feeling'))]),
        ("Qibla Wall Detailing", answers.get('prayer_qibla_wall')),
        ("Courtyard Required", answers.get('courtyard_required')),
        ("Courtyard Elements Desired", answers.get('courtyard_elements'))
    ]
    t_ht_prayer = create_qa_table([q for q in ht_prayer_qa if q[1] is not None and q[1] != ""], styles)
    if t_ht_prayer:
        story.append(t_ht_prayer)
        story.append(Spacer(1, 10))

    # =========================================================
    # 5. CHAPTER 4: BEDROOMS & PRIVATE SPACES
    # =========================================================
    story.append(PageBreak())
    story.append(Paragraph("04. BEDROOMS & PRIVATE SPACES", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))

    # Selected Bedroom Visual Reference
    bed_vis = selected_visuals.get('bedroom')
    if bed_vis:
        story.append(Paragraph("Selected Bedroom & Wardrobe Design Reference", styles['SectionHeading']))
        bed_img_rel = bed_vis.get('bedroom_image_url', '').lstrip('/')
        ward_img_rel = bed_vis.get('wardrobe_image_url', '').lstrip('/')
        
        bed_imgs = []
        if os.path.exists(bed_img_rel):
            bed_imgs.append(RLImage(bed_img_rel, width=150, height=95))
        if os.path.exists(ward_img_rel):
            bed_imgs.append(RLImage(ward_img_rel, width=150, height=95))

        bed_table_data = [
            [
                bed_imgs[0] if len(bed_imgs) > 0 else "",
                bed_imgs[1] if len(bed_imgs) > 1 else "",
                [
                    Paragraph(f"<b>Style {bed_vis.get('style_number', '')}: {bed_vis.get('style_name', '')}</b>", styles['VisualStyleTitle']),
                    Spacer(1, 3),
                    Paragraph("Bedroom & Dressing Paired Reference", styles['VisualDesc'])
                ]
            ]
        ]
        t_bed_vis = Table(bed_table_data, colWidths=[155, 155, 177])
        t_bed_vis.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER)
        ]))
        story.append(t_bed_vis)
        story.append(Spacer(1, 10))

    # Master Bedroom
    story.append(Paragraph("Master Bedroom Specifications", styles['SectionHeading']))
    mb_qa = [
        ("Floor Location", answers.get('mb_floor')),
        ("Preferred Style", answers.get('mb_style')),
        ("Desired Mood / Feeling", answers.get('mb_mood')),
        ("Bed Size", answers.get('mb_bed_size')),
        ("Additional Elements", answers.get('mb_elements')),
        ("Wardrobe / Dressing Type", answers.get('mb_wardrobe_type')),
        ("Wardrobe Accessories", answers.get('mb_wardrobe_acc')),
        ("Bathroom Features", answers.get('mb_bathroom_features')),
        ("Master Suite Notes", answers.get('mb_notes'))
    ]
    t_mb = create_qa_table([q for q in mb_qa if q[1] is not None and q[1] != ""], styles)
    if t_mb:
        story.append(t_mb)
        story.append(Spacer(1, 8))

    # Parent's Room
    if answers.get('has_parent_room') == 'Yes':
        story.append(Paragraph("Parent’s Room Specifications", styles['SectionHeading']))
        pb_qa = [
            ("Floor Location", answers.get('pb_floor')),
            ("Preferred Style", answers.get('pb_style')),
            ("Desired Mood / Feeling", answers.get('pb_mood')),
            ("Bed Size", answers.get('pb_bed_size')),
            ("Additional Elements", answers.get('pb_elements')),
            ("Mobility / Safety Considerations", answers.get('pb_mobility')),
            ("Bathroom Features", answers.get('pb_bathroom_features')),
            ("Parent's Room Notes", answers.get('pb_notes'))
        ]
        t_pb = create_qa_table([q for q in pb_qa if q[1] is not None and q[1] != ""], styles)
        if t_pb:
            story.append(t_pb)
            story.append(Spacer(1, 8))

    # Dynamic Additional Bedrooms
    if dynamic_rooms:
        for idx, room in enumerate(dynamic_rooms):
            r_ans = room.get('answers', {})
            story.append(Paragraph(f"{room.get('room_name', f'Additional Bedroom {idx+1}')} ({r_ans.get('intended_user', 'Guest')})", styles['SectionHeading']))
            dyn_qa = [
                ("Intended User", r_ans.get('intended_user')),
                ("Floor Location", r_ans.get('floor_location')),
                ("Design Style", r_ans.get('design_style')),
                ("Desired Mood / Feeling", r_ans.get('mood_feeling')),
                ("Bed Size", r_ans.get('bed_size')),
                ("Colour Preference", r_ans.get('colour_preference')),
                ("Additional Elements Needed", r_ans.get('additional_elements')),
                ("Wardrobe & Dressing", r_ans.get('wardrobe_type')),
                ("Bathroom Features", r_ans.get('bathroom_features')),
                ("Special Notes", r_ans.get('special_notes'))
            ]
            t_dyn = create_qa_table([q for q in dyn_qa if q[1] is not None and q[1] != ""], styles)
            if t_dyn:
                story.append(t_dyn)
                story.append(Spacer(1, 6))

    # =========================================================
    # 6. CHAPTER 5: KITCHEN & SERVICE AREAS
    # =========================================================
    story.append(PageBreak())
    story.append(Paragraph("05. KITCHEN & SERVICE AREAS", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))

    # Selected Kitchen Visual Reference
    kit_vis = selected_visuals.get('kitchen')
    if kit_vis:
        img_rel = kit_vis.get('image_url', '').lstrip('/')
        if os.path.exists(img_rel):
            kit_table_data = [
                [
                    RLImage(img_rel, width=220, height=130),
                    [
                        Paragraph(f"<b>Style {kit_vis.get('style_number', '')}: {kit_vis.get('style_name', '')}</b>", styles['VisualStyleTitle']),
                        Spacer(1, 4),
                        Paragraph("Selected Kitchen Design Style Reference", styles['VisualDesc'])
                    ]
                ]
            ]
            t_kit_vis = Table(kit_table_data, colWidths=[230, 257])
            t_kit_vis.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER)
            ]))
            story.append(t_kit_vis)
            story.append(Spacer(1, 10))

    # Main Kitchen
    story.append(Paragraph("5.1 Main Kitchen", styles['SectionHeading']))
    mk_qa = [
        ("Visibility from Living / Dining", answers.get('mk_visibility')),
        ("Kitchen Layout", answers.get('mk_layout')),
        ("Breakfast Counter / Bar Seating", answers.get('mk_breakfast_counter')),
        ("Counter Seatings Count", answers.get('mk_seatings')),
        ("Storage Requirement", answers.get('mk_storage')),
        ("Planned Appliances", answers.get('mk_appliances')),
        ("Pantry & Provisions Accessories", answers.get('mk_pantry_acc')),
        ("Utensil Organisation Accessories", answers.get('mk_utensil_acc')),
        ("Corner & Cabinet Accessories", answers.get('mk_corner_acc')),
        ("Sink, Cleaning & Waste Accessories", answers.get('mk_sink_acc')),
        ("Cooking Intensity", answers.get('mk_cooking_intensity')),
        ("Countertop Material", answers.get('mk_countertop'))
    ]
    t_mk = create_qa_table([q for q in mk_qa if q[1] is not None and q[1] != ""], styles)
    if t_mk:
        story.append(t_mk)
        story.append(Spacer(1, 8))

    # Working Kitchen, Utility & Store
    story.append(Paragraph("5.2 Working Kitchen, Utility & Store Room", styles['SectionHeading']))
    service_qa = [
        ("Working Kitchen Required", answers.get('wk_required')),
        ("Working Kitchen Layout", answers.get('wk_layout')),
        ("Working Kitchen Cooking Intensity", answers.get('wk_cooking_intensity')),
        ("Utility Room Required", answers.get('utility_required')),
        ("Utility Work Functions", answers.get('utility_functions')),
        ("Cloth Drying Preference", answers.get('utility_cloth_drying')),
        ("Separate Store Room Required", answers.get('store_required')),
        ("Store Storage Purpose", answers.get('store_purpose')),
        ("Storage System Preference", answers.get('store_system'))
    ]
    t_serv = create_qa_table([q for q in service_qa if q[1] is not None and q[1] != ""], styles)
    if t_serv:
        story.append(t_serv)
        story.append(Spacer(1, 10))

    # =========================================================
    # 7. CHAPTER 6: SYSTEMS, FINISHES & STYLING
    # =========================================================
    story.append(PageBreak())
    story.append(Paragraph("06. SYSTEMS, FINISHES & STYLING PREFERENCES", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))

    story.append(Paragraph("6.1 Lighting, Flooring & Wall Finishes", styles['SectionHeading']))
    sys_qa = [
        ("Overall Lighting Mood", answers.get('lighting_mood')),
        ("Lighting Control Preference", answers.get('lighting_control')),
        ("Layered Lighting Approach", answers.get('layered_lighting_approach')),
        ("Smart Lighting Scenes", answers.get('smart_lighting_scenes')),
        ("Flooring — Living & Common Areas", answers.get('flooring_living')),
        ("Flooring — Bedrooms", answers.get('flooring_bedrooms')),
        ("Verandah / Sit-out Flooring", answers.get('flooring_verandah')),
        ("Tile / Slab Size Preference", answers.get('tile_slab_size')),
        ("Overall Flooring Tone", answers.get('overall_flooring_tone')),
        ("False-Ceiling Material", answers.get('false_ceiling_material')),
        ("Wall Finish Preference", answers.get('wall_finish_preference'))
    ]
    t_sys = create_qa_table([q for q in sys_qa if q[1] is not None and q[1] != ""], styles)
    if t_sys:
        story.append(t_sys)
        story.append(Spacer(1, 8))

    story.append(Paragraph("6.2 Soft Furnishings, Security & Smart Home Automation", styles['SectionHeading']))
    sec_qa = [
        ("Curtain & Drapery Preference", answers.get('curtain_preference')),
        ("Upholstery Material", answers.get('upholstery_material')),
        ("Colour & Texture Palette", answers.get('colour_texture_palette')),
        ("Rugs & Carpets", answers.get('rugs_carpets')),
        ("Artwork & Accessories", answers.get('artwork_accessories')),
        ("Home Automation Scope", answers.get('automation_interest')),
        ("CCTV Coverage", answers.get('cctv_coverage')),
        ("Access Control", answers.get('access_control')),
        ("Gate Security", answers.get('gate_security')),
        ("Alarm & Sensors", answers.get('alarm_sensors')),
        ("Backup Power", answers.get('backup_power'))
    ]
    t_sec = create_qa_table([q for q in sec_qa if q[1] is not None and q[1] != ""], styles)
    if t_sec:
        story.append(t_sec)
        story.append(Spacer(1, 10))

    # =========================================================
    # 8. CHAPTER 7: OUTDOOR & SWIMMING POOL
    # =========================================================
    story.append(PageBreak())
    story.append(Paragraph("07. OUTDOOR, LANDSCAPE & SWIMMING POOL", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))

    story.append(Paragraph("7.1 Landscape & External Works", styles['SectionHeading']))
    land_qa = [
        ("Landscape Areas to Include", answers.get('landscape_areas')),
        ("Intended Outdoor Use", answers.get('outdoor_use')),
        ("Outdoor Seating / Gazebo", answers.get('outdoor_seating_gazebo')),
        ("Outdoor Desired Feeling", answers.get('outdoor_feeling')),
        ("Preferred Landscape Style", answers.get('landscape_style')),
        ("Greenery & Open Space Balance", answers.get('greenery_balance')),
        ("Outdoor Features Desired", answers.get('outdoor_elements_desired')),
        ("Front-Yard Privacy", answers.get('front_yard_privacy')),
        ("Paving Character", answers.get('paving_character')),
        ("Rain, Drainage & Irrigation", answers.get('drainage_irrigation'))
    ]
    t_land = create_qa_table([q for q in land_qa if q[1] is not None and q[1] != ""], styles)
    if t_land:
        story.append(t_land)
        story.append(Spacer(1, 8))

    story.append(Paragraph("7.2 Swimming Pool Specifications", styles['SectionHeading']))
    pool_qa = [
        ("Pool Requirement", answers.get('pool_requirement')),
        ("Primary Pool Use", answers.get('pool_primary_use')),
        ("Preferred Pool Type", answers.get('pool_type')),
        ("Preferred Location", answers.get('pool_location')),
        ("Desired Pool Feeling", answers.get('pool_feeling')),
        ("Pool Privacy", answers.get('pool_privacy')),
        ("Approximate Size & Depth", [format_val(answers.get('pool_size')), format_val(answers.get('pool_depth'))]),
        ("Pool Finish", answers.get('pool_finish')),
        ("Poolside Amenities", answers.get('poolside_amenities')),
        ("Special Features", answers.get('pool_special_features')),
        ("Pool Safety & Lighting", [format_val(answers.get('pool_safety')), format_val(answers.get('pool_lighting'))]),
        ("Maintenance Preference", answers.get('pool_maintenance')),
        ("Pool Notes", answers.get('pool_additional_notes'))
    ]
    t_pool = create_qa_table([q for q in pool_qa if q[1] is not None and q[1] != ""], styles)
    if t_pool:
        story.append(t_pool)
        story.append(Spacer(1, 10))

    # =========================================================
    # 9. CHAPTER 8: FINAL NOTES & DESIGN REFERENCES SUMMARY
    # =========================================================
    story.append(Paragraph("08. ADDITIONAL NOTES & SELECTED REFERENCES", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))

    story.append(Paragraph("8.1 Additional Notes from Client", styles['SectionHeading']))
    custom_notes = answers.get('final_custom_notes', 'None provided.') or 'None provided.'
    story.append(Paragraph(custom_notes, styles['AnswerValue']))
    story.append(Spacer(1, 14))

    # Selected Visuals Table Summary
    story.append(Paragraph("8.2 Visual Reference Selection Summary", styles['SectionHeading']))
    vis_summary_data = [
        [
            Paragraph("<b>Category</b>", styles['QuestionLabel']),
            Paragraph("<b>Selected Style</b>", styles['QuestionLabel']),
            Paragraph("<b>Style #</b>", styles['QuestionLabel'])
        ],
        [
            Paragraph("Exterior Architecture", styles['AnswerValue']),
            Paragraph(selected_visuals.get('exterior', {}).get('style_name', 'Not selected'), styles['AnswerValue']),
            Paragraph(str(selected_visuals.get('exterior', {}).get('style_number', '—')), styles['AnswerValue'])
        ],
        [
            Paragraph("Formal Living & Dining", styles['AnswerValue']),
            Paragraph(selected_visuals.get('formal_living_dining', {}).get('style_name', 'Not selected'), styles['AnswerValue']),
            Paragraph(str(selected_visuals.get('formal_living_dining', {}).get('style_number', '—')), styles['AnswerValue'])
        ],
        [
            Paragraph("Bedrooms & Dressing", styles['AnswerValue']),
            Paragraph(selected_visuals.get('bedroom', {}).get('style_name', 'Not selected'), styles['AnswerValue']),
            Paragraph(str(selected_visuals.get('bedroom', {}).get('style_number', '—')), styles['AnswerValue'])
        ],
        [
            Paragraph("Kitchen Design", styles['AnswerValue']),
            Paragraph(selected_visuals.get('kitchen', {}).get('style_name', 'Not selected'), styles['AnswerValue']),
            Paragraph(str(selected_visuals.get('kitchen', {}).get('style_number', '—')), styles['AnswerValue'])
        ]
    ]
    t_vis_sum = Table(vis_summary_data, colWidths=[160, 260, 67])
    t_vis_sum.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP')
    ]))
    story.append(t_vis_sum)
    story.append(Spacer(1, 25))

    # Sign-off box
    sign_data = [
        [
            Paragraph("<b>Submitted for Architectural Review:</b><br/>Shameer Associates Design Team", styles['AnswerValue']),
            Paragraph(f"<b>Client Signature / Confirmation:</b><br/>{client_name} (Digitally Submitted)", styles['AnswerValue'])
        ]
    ]
    t_sign = Table(sign_data, colWidths=[240, 247])
    t_sign.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, COLOR_BORDER),
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    story.append(t_sign)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()


def generate_architect_pdf_bytes(project_data, schema):
    """
    Generate an Architect Project Workspace PDF including:
    - Project UID, status, assigned architect
    - Client answers & visual references
    - Architect internal notes
    - Status history & edit log
    """
    session_data = project_data.get('session') or {}
    notes = project_data.get('notes', [])
    status_history = project_data.get('status_history', [])
    edit_history = project_data.get('edit_history', [])
    status = project_data.get('status', 'new_submission')
    status_label = status.replace('_', ' ').title()
    project_uid = project_data.get('project_uid', 'SA-2026-0000')
    assigned_architect = project_data.get('assigned_architect', {}) or {}
    architect_name = assigned_architect.get('full_name', 'Shameer Associates Team')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = get_custom_styles()
    story = []

    answers = session_data.get('answers', {})
    family_members = session_data.get('family_members', [])
    dynamic_rooms = session_data.get('dynamic_rooms', [])
    selected_visuals = session_data.get('selected_visuals', {})
    client_name = project_data.get('client_name') or answers.get('client_name', 'Client') or 'Client'
    location = project_data.get('location') or answers.get('project_location', 'Kerala, India') or 'Kerala, India'
    date_str = datetime.now().strftime('%d %B %Y')

    # 1. COVER PAGE
    story.append(Spacer(1, 15))
    logo_path = 'static/brand/shameer_associates_logo.png'
    if os.path.exists(logo_path):
        story.append(RLImage(logo_path, width=100, height=100))
        story.append(Spacer(1, 10))

    story.append(Paragraph("SHAMEER ASSOCIATES", styles['CoverBrand']))
    story.append(Paragraph("ARCHITECTURE • INTERIORS • LANDSCAPE", styles['CoverTagline']))
    story.append(HRFlowable(width="30%", thickness=1.5, color=COLOR_ACCENT, spaceAfter=15, spaceBefore=5))
    
    story.append(Paragraph("ARCHITECT PROJECT BRIEF & SPECIFICATION", styles['CoverMotto']))
    story.append(Paragraph(f"PROJECT ID: {project_uid}", styles['CoverDocTitle']))
    story.append(Spacer(1, 10))

    meta_text = (
        f"<b>Client Name:</b> {client_name}<br/>"
        f"<b>Project Location:</b> {location}<br/>"
        f"<b>Project Status:</b> {status_label}<br/>"
        f"<b>Assigned Architect:</b> {architect_name}<br/>"
        f"<b>Generated Date:</b> {date_str}"
    )
    story.append(Paragraph(meta_text, styles['CoverMeta']))
    story.append(Spacer(1, 25))

    # Architectural Overview Card
    overview_table_data = [
        [
            Paragraph("<b>Project UID</b>", styles['QuestionLabel']),
            Paragraph(project_uid, styles['AnswerValue']),
            Paragraph("<b>Current Status</b>", styles['QuestionLabel']),
            Paragraph(status_label, styles['AnswerValue'])
        ],
        [
            Paragraph("<b>Client Name</b>", styles['QuestionLabel']),
            Paragraph(client_name, styles['AnswerValue']),
            Paragraph("<b>Location</b>", styles['QuestionLabel']),
            Paragraph(location, styles['AnswerValue'])
        ],
        [
            Paragraph("<b>Assigned Architect</b>", styles['QuestionLabel']),
            Paragraph(architect_name, styles['AnswerValue']),
            Paragraph("<b>Submission Date</b>", styles['QuestionLabel']),
            Paragraph(str(session_data.get('submitted_at', '—')), styles['AnswerValue'])
        ]
    ]
    t_ov = Table(overview_table_data, colWidths=[110, 133, 110, 134])
    t_ov.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    story.append(t_ov)
    story.append(PageBreak())

    # Generate standard questionnaire contents
    # Client Profile
    story.append(Paragraph("01. CLIENT & PROJECT OVERVIEW", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))
    client_qa = [
        ("Client Name", client_name),
        ("Contact Number", answers.get('contact_number')),
        ("Email Address", answers.get('email_address')),
        ("Primary Occupation", answers.get('occupation')),
        ("Project Location", location),
        ("Project Type", answers.get('project_type')),
        ("Expected Area (sq ft)", answers.get('expected_builtup_area')),
        ("Total Budget", answers.get('total_budget'))
    ]
    t_c = create_qa_table(client_qa, styles)
    if t_c:
        story.append(t_c)
    story.append(Spacer(1, 15))

    # Dynamic family members if present
    if family_members:
        story.append(Paragraph("1.2 Family Profile", styles['SectionHeading']))
        fam_headers = ["User Group", "Count", "Gender", "Age Range", "Special Notes"]
        fam_rows = [[Paragraph(f"<b>{h}</b>", styles['QuestionLabel']) for h in fam_headers]]
        for m in family_members:
            fam_rows.append([
                Paragraph(m.get('user_group', ''), styles['AnswerValue']),
                Paragraph(str(m.get('count', 1)), styles['AnswerValue']),
                Paragraph(m.get('gender', '—'), styles['AnswerValue']),
                Paragraph(m.get('age_range', '—'), styles['AnswerValue']),
                Paragraph(m.get('special_note', '—'), styles['AnswerValue'])
            ])
        t_fam = Table(fam_rows, colWidths=[100, 45, 90, 85, 167])
        t_fam.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_LIGHT),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        story.append(t_fam)
        story.append(Spacer(1, 15))

    # Selected Visual References Summary
    story.append(Paragraph("02. VISUAL REFERENCES SUMMARY", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))
    vis_summary_data = [
        [
            Paragraph("<b>Category</b>", styles['QuestionLabel']),
            Paragraph("<b>Selected Style</b>", styles['QuestionLabel']),
            Paragraph("<b>Style #</b>", styles['QuestionLabel'])
        ],
        [
            Paragraph("Exterior Architecture", styles['AnswerValue']),
            Paragraph(selected_visuals.get('exterior', {}).get('style_name', 'Not selected'), styles['AnswerValue']),
            Paragraph(str(selected_visuals.get('exterior', {}).get('style_number', '—')), styles['AnswerValue'])
        ],
        [
            Paragraph("Formal Living & Dining", styles['AnswerValue']),
            Paragraph(selected_visuals.get('formal_living_dining', {}).get('style_name', 'Not selected'), styles['AnswerValue']),
            Paragraph(str(selected_visuals.get('formal_living_dining', {}).get('style_number', '—')), styles['AnswerValue'])
        ],
        [
            Paragraph("Bedrooms & Dressing", styles['AnswerValue']),
            Paragraph(selected_visuals.get('bedroom', {}).get('style_name', 'Not selected'), styles['AnswerValue']),
            Paragraph(str(selected_visuals.get('bedroom', {}).get('style_number', '—')), styles['AnswerValue'])
        ],
        [
            Paragraph("Kitchen Design", styles['AnswerValue']),
            Paragraph(selected_visuals.get('kitchen', {}).get('style_name', 'Not selected'), styles['AnswerValue']),
            Paragraph(str(selected_visuals.get('kitchen', {}).get('style_number', '—')), styles['AnswerValue'])
        ]
    ]
    t_vis_sum = Table(vis_summary_data, colWidths=[160, 260, 67])
    t_vis_sum.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP')
    ]))
    story.append(t_vis_sum)
    story.append(Spacer(1, 20))

    # ARCHITECT INTERNAL NOTES SECTION
    story.append(Paragraph("03. ARCHITECT INTERNAL NOTES", styles['ChapterHeading']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))

    if notes:
        note_headers = ["Category", "Note Content", "Author", "Date"]
        note_rows = [[Paragraph(f"<b>{h}</b>", styles['QuestionLabel']) for h in note_headers]]
        for n in notes:
            n_type = n.get('note_type', 'general').upper()
            n_content = n.get('content', '')
            n_author = n.get('author_name', 'Architect')
            n_date = str(n.get('created_at', ''))[:16]
            note_rows.append([
                Paragraph(n_type, styles['AnswerValue']),
                Paragraph(n_content, styles['AnswerValue']),
                Paragraph(n_author, styles['AnswerValue']),
                Paragraph(n_date, styles['AnswerValue'])
            ])
        t_notes = Table(note_rows, colWidths=[80, 240, 87, 80])
        t_notes.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_LIGHT),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        story.append(t_notes)
    else:
        story.append(Paragraph("No internal notes recorded.", styles['AnswerValue']))

    story.append(Spacer(1, 20))

    # STATUS & AUDIT HISTORY
    if status_history:
        story.append(Paragraph("04. STATUS WORKFLOW HISTORY", styles['ChapterHeading']))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8, spaceBefore=2))
        st_headers = ["From Status", "To Status", "Changed By", "Date & Note"]
        st_rows = [[Paragraph(f"<b>{h}</b>", styles['QuestionLabel']) for h in st_headers]]
        for sh in status_history:
            f_st = sh.get('from_status', '').replace('_', ' ').title()
            t_st = sh.get('to_status', '').replace('_', ' ').title()
            c_by = sh.get('changed_by_name', 'Architect')
            c_note = f"{sh.get('changed_at', '')[:16]} — {sh.get('note', '')}" if sh.get('note') else str(sh.get('changed_at', ''))[:16]
            st_rows.append([
                Paragraph(f_st, styles['AnswerValue']),
                Paragraph(t_st, styles['AnswerValue']),
                Paragraph(c_by, styles['AnswerValue']),
                Paragraph(c_note, styles['AnswerValue'])
            ])
        t_sh = Table(st_rows, colWidths=[100, 100, 100, 187])
        t_sh.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_BG_LIGHT),
            ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP')
        ]))
        story.append(t_sh)
        story.append(Spacer(1, 25))

    # Sign-off box
    sign_data = [
        [
            Paragraph(f"<b>Architect Verification:</b><br/>{architect_name} (Shameer Associates)", styles['AnswerValue']),
            Paragraph(f"<b>Project Status Confirmed:</b><br/>{status_label} ({date_str})", styles['AnswerValue'])
        ]
    ]
    t_sign = Table(sign_data, colWidths=[240, 247])
    t_sign.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, COLOR_BORDER),
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    story.append(t_sign)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()

