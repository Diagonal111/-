import io
import re
import uuid
import zipfile
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import HTTPException
from .store import FILES

MAX_FILE = 12 * 1024 * 1024


def save_image(content):
    if len(content)>MAX_FILE:
        raise HTTPException(413,'单张照片请控制在 12 MB 以内。')
    try:
        with Image.open(io.BytesIO(content)) as original:
            if original.width*original.height>35_000_000:
                raise HTTPException(400,'图片像素过大，请先缩小尺寸。')
            image=ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((2200,2200))
            name=uuid.uuid4().hex+'.jpg'
            image.save(FILES/name,'JPEG',quality=90)
            return name
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError):
        raise HTTPException(400,'图片无法读取，请使用 JPG 或 PNG 照片。')


def safe_archive(content):
    try:
        archive=zipfile.ZipFile(io.BytesIO(content))
        if len(archive.infolist())>5000 or sum(i.file_size for i in archive.infolist())>80*1024*1024:
            archive.close()
            raise HTTPException(413,'文件解压内容过大，请分成较小文件。')
        return archive
    except zipfile.BadZipFile:
        raise HTTPException(400,'Office 文件损坏或格式不正确，请另存为 .xlsx / .docx。')


def extract_material(filename,content):
    ext=Path(filename).suffix.lower()
    images=[]
    warnings=[]
    items=[]
    text=''
    if ext in ('.jpg','.jpeg','.png'):
        images=[save_image(content)]
    elif ext=='.xlsx':
        import openpyxl
        with safe_archive(content) as archive:
            media=[n for n in archive.namelist() if n.startswith('xl/media/') and n.lower().endswith(('.jpg','.jpeg','.png'))]
            for name in media[:8]:
                images.append(save_image(archive.read(name)))
            if media:
                warnings.append('Excel 嵌入图片已提取。请校对图片与题目的对应关系。')
        workbook=openpyxl.load_workbook(io.BytesIO(content),read_only=True,data_only=True)
        parts=[]
        truncated=False
        for sheet in workbook.worksheets[:8]:
            rows=[]
            for row in sheet.iter_rows():
                values=[str(cell.value if cell.value is not None else '')[:8000] for cell in row[:30]]
                if any(values):
                    rows.append(values)
                if len(rows)>=150:
                    truncated=True
                    break
            parts.append(f'工作表：{sheet.title}\n'+'\n'.join(' | '.join(r) for r in rows))
            if rows:
                mapped=map_columns(rows)
                for item in mapped:
                    item['source']=f'{filename} · {sheet.title}'
                items.extend(mapped)
        workbook.close()
        text='\n\n'.join(parts)
        if truncated:
            warnings.append('每个工作表本次最多读取150行，请拆分超出部分后导入。')
    elif ext=='.docx':
        from docx import Document
        with safe_archive(content) as archive:
            media=[n for n in archive.namelist() if n.startswith('word/media/') and n.lower().endswith(('.jpg','.jpeg','.png'))]
            for name in media[:8]:
                images.append(save_image(archive.read(name)))
            xml=archive.read('word/document.xml').decode('utf-8') if 'word/document.xml' in archive.namelist() else ''
            if '<m:oMath' in xml:
                warnings.append('文档含 Office 数学公式，首版纯文字提取可能不完整；请对照原文件，必要时补充公式截图。')
        document=Document(io.BytesIO(content))
        # Keep paragraph/table order using the document body's actual XML order.
        parts=[]
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        for child in document.element.body:
            lines=[''.join(n.itertext()) for n in child.findall('.//w:t',ns)]
            parts.append(' '.join(lines))
        text='\n'.join(parts)
    else:
        raise HTTPException(400,'当前支持 .xlsx、.docx、JPG 和 PNG。旧版 Office 请先另存。')
    if len(text)>45000:
        text=text[:45000]
        warnings.append('本次仅处理前45000个字符，请拆分剩余材料后导入。')
    if len(items)>30:
        items=items[:30]
        warnings.append('本次预览前30道结构化题目，请拆分剩余题目。')
    return {'text':text,'images':images,'items':items,'warnings':warnings}


def map_columns(rows):
    aliases={
        'body':['题干','题目','题目内容','body','question'],
        'title':['标题','title'], 'answer':['答案','参考答案','正确答案','answer'],
        'explanation':['解析','解答','explanation'], 'type':['题型','类型','type'],
        'knowledge_id':['知识点','knowledge_id'],
    }
    head=[str(v).strip().lower() for v in rows[0]]
    columns={key:next((i for i,h in enumerate(head) if h in values),None) for key,values in aliases.items()}
    if columns['body'] is None:
        return []
    result=[]
    for row in rows[1:]:
        item={key:row[i] if i is not None and i<len(row) else '' for key,i in columns.items()}
        if not item['body'].strip():
            continue
        options=[]
        for letter in 'ABCDEFGH':
            i=next((i for i,h in enumerate(head) if h in (letter.lower(),'选项'+letter.lower())),None)
            if i is not None and i<len(row) and row[i]:
                options.append(row[i])
        item['options']=options
        item['type']=normalize_type(item['type'],options)
        item['title']=item['title'] or re.sub(r'\s+',' ',item['body'])[:32]
        if item['type']=='boolean' and not options:
            item['options']=['正确','错误']
        item['minutes']=12 if item['type']=='calculation' else 3
        item['warnings']=[]
        result.append(item)
    return result


def normalize_type(value,options=None):
    aliases={'单选':'single','单选题':'single','选择题':'single','多选':'multiple','多选题':'multiple','判断':'boolean','判断题':'boolean','计算':'calculation','计算题':'calculation','综合题':'calculation'}
    value=aliases.get(str(value).strip(),str(value).strip())
    return value if value in ('single','multiple','boolean','calculation') else 'single' if options else 'calculation'
