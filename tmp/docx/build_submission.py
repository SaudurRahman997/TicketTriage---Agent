from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.section import WD_SECTION

OUT = r'output\word\i230540_submission.docx'
doc = Document()
sec = doc.sections[0]
sec.top_margin = Inches(.62); sec.bottom_margin = Inches(.62)
sec.left_margin = Inches(.72); sec.right_margin = Inches(.72)

# Base typography
normal = doc.styles['Normal']; normal.font.name = 'Aptos'; normal.font.size = Pt(9.5); normal.font.color.rgb = RGBColor(35,45,58)
normal.paragraph_format.space_after = Pt(4)
for stylename in ['Title','Heading 1','Heading 2']:
    s=doc.styles[stylename]; s.font.name='Aptos Display'; s.font.color.rgb=RGBColor(0,0,0)
    s._element.rPr.rFonts.set(qn('w:ascii'),'Aptos Display'); s._element.rPr.rFonts.set(qn('w:hAnsi'),'Aptos Display')
doc.styles['Title'].font.size=Pt(27); doc.styles['Title'].font.bold=True; doc.styles['Title'].paragraph_format.space_after=Pt(0)
doc.styles['Heading 1'].font.size=Pt(13); doc.styles['Heading 1'].font.bold=True
doc.styles['Heading 1'].paragraph_format.space_before=Pt(10); doc.styles['Heading 1'].paragraph_format.space_after=Pt(5)

def shade(cell, fill):
    tcPr=cell._tc.get_or_add_tcPr(); shd=OxmlElement('w:shd'); shd.set(qn('w:fill'),fill); tcPr.append(shd)
def borders(table):
    tblPr=table._tbl.tblPr; b=OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        e=OxmlElement('w:'+edge); e.set(qn('w:val'),'single'); e.set(qn('w:sz'),'5'); e.set(qn('w:color'),'D9E0E8'); b.append(e)
    tblPr.append(b)
def set_cell(cell, text, *, bold=False, color=None, size=9):
    cell.text=''; p=cell.paragraphs[0]; p.paragraph_format.space_after=Pt(0); p.paragraph_format.space_before=Pt(0)
    run=p.add_run(text); run.bold=bold; run.font.name='Aptos'; run.font.size=Pt(size)
    if color: run.font.color.rgb=RGBColor(*color)
    cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
    tcPr=cell._tc.get_or_add_tcPr(); mar=OxmlElement('w:tcMar')
    for side,val in [('top','75'),('start','110'),('bottom','75'),('end','110')]:
        node=OxmlElement('w:'+side); node.set(qn('w:w'),val); node.set(qn('w:type'),'dxa'); mar.append(node)
    tcPr.append(mar)
def kv(title, rows):
    h=doc.add_paragraph(title, style='Heading 1'); h.paragraph_format.keep_with_next=True
    t=doc.add_table(rows=0, cols=2); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.autofit=False
    t.columns[0].width= Inches(1.72); t.columns[1].width= Inches(5.88); borders(t)
    for label,val in rows:
        cells=t.add_row().cells; cells[0].width= Inches(1.72); cells[1].width= Inches(5.88)
        shade(cells[0],'EDF2F7'); set_cell(cells[0],label,bold=True,color=(35,55,78))
        set_cell(cells[1],val)
    doc.add_paragraph().paragraph_format.space_after=Pt(0)

p=doc.add_paragraph(style='Title'); p.add_run('TicketTriage Sentinel')
p=doc.add_paragraph(); p.paragraph_format.space_after=Pt(8)
r=p.add_run('AGENT ARENA  |  ASSIGNMENT 1'); r.bold=True; r.font.size=Pt(9); r.font.color.rgb=RGBColor(76,91,108)
p=doc.add_paragraph('Submission summary  |  Roll number i230540'); p.paragraph_format.space_after=Pt(4)
p.runs[0].font.size=Pt(11); p.runs[0].font.color.rgb=RGBColor(76,91,108)

kv('Student and project',[
('Full name','TODO - enter full name as shown in university records'),('Roll number','i230540'),('Class / section','TODO - enter class and section'),('University email','TODO - enter university email'),('GitHub username','SaudurRahman997'),('Agent name','TicketTriage Sentinel'),('Domain','Support-Ticket Triage')])
kv('Repository and live deployment',[
('GitHub repository','https://github.com/SaudurRahman997/TicketTriage---Agent'),('Final commit hash','TODO - update after final source commit and deployment'),('Working agent interface','https://tickettriageagent.vercel.app/'),('Health endpoint (GET)','https://tickettriageagent.vercel.app/health'),('Arena endpoint (POST)','https://tickettriageagent.vercel.app/arena/run'),('Manifest endpoint (GET)','https://tickettriageagent.vercel.app/arena/manifest'),('API documentation','https://tickettriageagent.vercel.app/docs'),('Hosting provider','Vercel')])
kv('Model, example, and limitations',[
('Default model / provider','TODO - verify the production default at /models before submission'),('Other available models','TODO - copy the configured model list from /models'),('Example input','Triage ticket T-1002 and draft a short reply.'),('Expected result','Reads the named ticket, classifies it, saves an unsent draft reply in the sandbox, and reports only confirmed actions.'),('Cold-start / restart limits','Conversation history is held in memory. Vercel may use a fresh or separate function instance, so history may not persist; verify multi-turn clarification on the deployed app.')])
kv('Evaluation and submission status',[
('Instructor repository access','TODO - record pending or accepted after inviting the instructor'),('Public test results','evaluation/public_results.md - rerun against the final deployed commit'),('Model comparison','Expected comparison is in README.md; measured two-model results are still required for the assignment.')])

p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(5); p.paragraph_format.space_after=Pt(0)
r=p.add_run('Before submission: '); r.bold=True
p.add_run('Complete every TODO above and copy the final values and links to SUBMISSION.md. Upload this document separately with i230540.zip, containing one top-level i230540/ project folder. Exclude .env, .venv/, .git/, caches, and API keys. Invite the instructor to the private repository and confirm Google Classroom shows Turned in.')
# Footer page field
footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
fr=footer.add_run('TicketTriage Sentinel  |  Assignment 1  |  '); fr.font.name='Aptos'; fr.font.size=Pt(8); fr.font.color.rgb=RGBColor(105,115,128)
fld=OxmlElement('w:fldSimple'); fld.set(qn('w:instr'),'PAGE'); footer._p.append(fld)
doc.core_properties.title='TicketTriage Sentinel Assignment 1 Submission Summary'
doc.core_properties.subject='Agent Arena Assignment 1 submission details'
doc.core_properties.author=''
doc.save(OUT)
print(OUT)
