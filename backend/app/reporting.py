"""Reproducible accounting reports; no currency aggregation or inferred FX."""
import io
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def render_pdf(report):
    stream=io.BytesIO()
    document=SimpleDocTemplate(stream,pagesize=(595.28,841.89),rightMargin=40,leftMargin=40,topMargin=44,bottomMargin=48,
        title='Financial reconciliation report',author='Reconcile')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TableBody',fontName='Helvetica',fontSize=8,leading=12,textColor=colors.HexColor('#394b60')))
    styles.add(ParagraphStyle(name='CaptionSmall',fontSize=9,leading=14,textColor=colors.HexColor('#6b7b8e')))
    job=report['job']
    body=[Paragraph('RECONCILE / FINANCIAL CONTROLS',styles['CaptionSmall']),Spacer(1,12),
        Paragraph(f"{escape(job['kind'].upper())} reconciliation",styles['Title']),
        Paragraph(f"Run {escape(job['id'])}",styles['CaptionSmall']),Spacer(1,18)]
    summary=job['result']
    body.append(Paragraph(f"{summary.get('total_records',0)} records | {summary.get('matched_records',0)} matched | {len(report['exceptions'])} exceptions",styles['Normal']))
    if report.get('accounting_statement'):
        body.extend([Spacer(1,20),Paragraph('Accounting statement',styles['Heading2'])])
        rows=[['Currency','Expected','Recorded','Difference']]
        for currency,values in report['accounting_statement']['balances_by_currency'].items():
            rows.append([currency,values['expected'],values['recorded'],values['difference']])
        body.append(styled_table(rows,[65,150,150,150],styles))
    body.extend([Spacer(1,20),Paragraph('Balances by currency',styles['Heading2'])])
    balances=[['Currency','Source','Target','Difference']]
    for currency,totals in summary.get('totals_by_currency',{}).items():
        balances.append([currency,totals['source'],totals['target'],totals['difference']])
    body.append(styled_table(balances,[65,150,150,150],styles))
    if report.get('simulation_by_currency'):
        body.extend([Spacer(1,18),Paragraph('Separately recorded simulation',styles['Heading2'])])
        rows=[['Currency','Cash adjustment','Simulated target','Remaining difference']]
        for currency,totals in report['simulation_by_currency'].items():
            rows.append([currency,totals['simulated_cash_adjustment'],totals['simulated_target_total'],totals['simulated_difference']])
        body.append(styled_table(rows,[65,150,150,150],styles))
    body.extend([Spacer(1,20),Paragraph('Exceptions requiring evidence or review',styles['Heading2'])])
    rows=[['Exception','Category','Amount','Currency','Status']]
    for exception in report['exceptions']:
        rows.append([exception['id'][:8].upper(),exception['category'].replace('_',' '),exception['amount'],exception['currency'],exception['status'].replace('_',' ')])
    if len(rows)==1:
        body.append(Paragraph('No exceptions recorded.',styles['Normal']))
    else:
        body.append(styled_table(rows,[67,160,85,53,150],styles))
    body.extend([Spacer(1,20),Paragraph(escape(report['note']),styles['CaptionSmall'])])
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#dae3eb'))
        canvas.line(40,38,555,38)
        canvas.setFont('Helvetica',8)
        canvas.setFillColor(colors.HexColor('#718196'))
        canvas.drawString(40,24,'Source records preserved | Simulations do not constitute external postings')
        canvas.drawRightString(555,24,f'Page {doc.page}')
    document.build(body,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()


def styled_table(rows,widths,styles):
    data=[[Paragraph(escape(str(value)),styles['TableBody']) for value in row] for row in rows]
    table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf3f0')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9),
        ('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#b6cec6')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f8fafb')])]))
    return table


def generic_report(title,columns,records):
    stream=io.BytesIO()
    doc=SimpleDocTemplate(stream,leftMargin=36,rightMargin=36,topMargin=40,bottomMargin=40)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TableBody',fontSize=7,leading=10))
    rows=[columns]+[[record.get(column,'') for column in columns] for record in records]
    width=(doc.width)/len(columns)
    body=[Paragraph(escape(title),styles['Title']),Spacer(1,16),styled_table(rows,[width]*len(columns),styles)]
    doc.build(body)
    return stream.getvalue()
