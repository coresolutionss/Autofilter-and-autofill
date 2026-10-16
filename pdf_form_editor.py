"""Local PDF-backed editor: data is passed as values, never executable HTML."""
import base64
from functools import lru_cache
import pymupdf
import streamlit.components.v2 as components
from form_config import field_labels
from pdf_form_layout import LAYOUTS, TEMPLATES

CSS = """
.scroll {overflow-x:auto; padding:0 0 16px;}
.sheet {position:relative;width:100%;min-width:0;max-width:1056px;margin:0 0 20px;
 background:white;box-shadow:0 1px 7px #0003;container-type:inline-size;}
.sheet img {width:100%;display:block;pointer-events:none;}
.sheet input {position:absolute;box-sizing:border-box;border:1px solid #B8944655;
 background:#F6F3E999;border-radius:1px;padding:0 2px;color:#102c48;
 font-family:Arial,sans-serif;font-size:1.45cqw;line-height:1.1;min-width:0;}
.sheet input:hover {background:#F3EBD8cc;border-color:#B89446;}
.sheet input:focus {outline:2px solid #B89446;background:#fff;z-index:2;}
.sheet input[type=checkbox] {padding:0;margin:0;accent-color:#14243B;cursor:pointer;}
.sheet-label {font:14px system-ui;color:#425269;margin:10px 0;}
"""
JS = """
export default function(component) {
 const {parentElement, data, setStateValue} = component;
 const root = parentElement.querySelector('.pdf-editor');
 root.replaceChildren();
 data.pages.forEach((page,index) => {
   const scroller=document.createElement('div');scroller.className='scroll';
   const sheet=document.createElement('div');sheet.className='sheet';
   const image=document.createElement('img');image.src=page.image;
   image.alt=data.title+' - original PDF page '+(index+1);
   sheet.appendChild(image);scroller.appendChild(sheet);root.appendChild(scroller);
   data.layout.filter(f=>f.page===index).forEach(f=>{
     const input=document.createElement('input');
     const choice=f.type==='choice', check=f.type==='checkbox';
     input.type=choice||check?'checkbox':'text';
     input.dataset.field=f.key;
     const label=data.labels[f.key]||f.key;
     input.setAttribute('aria-label',label+(choice?' - '+f.value:''));
     input.title=label+(choice?' - '+f.value:'');
     input.autocomplete='off';
     const r=f.rect;
     input.style.left=(r[0]/page.width*100)+'%';
     input.style.top=(r[1]/page.height*100)+'%';
     input.style.width=((r[2]-r[0])/page.width*100)+'%';
     input.style.height=((r[3]-r[1])/page.height*100)+'%';
     const value=String(data.values[f.key]||'');
     if(choice) input.checked=value.toLowerCase()===f.value;
     else if(check) input.checked=value==='yes';
     else input.value=value;
     input.addEventListener('change',()=>{
       const value=choice?(input.checked?f.value:''):check?(input.checked?'yes':''):input.value;
       setStateValue('edit',{key:f.key,value,nonce:Date.now()});
     });
     sheet.appendChild(input);
   });
 });
}
"""
pdf_editor = components.component('amb_original_pdf_editor',html='<div class="pdf-editor"></div>',css=CSS,js=JS)


@lru_cache(maxsize=4)
def template_pages(form_type):
    with pymupdf.open(TEMPLATES[form_type]) as doc:
        return [{'width':page.rect.width,'height':page.rect.height,
                 'image':'data:image/png;base64,'+base64.b64encode(
                     page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).tobytes('png')).decode('ascii')}
                for page in doc]


def render_editor(form_type, values, key, on_edit):
    return pdf_editor(key=key,data={'pages':template_pages(form_type),
        'layout':LAYOUTS[form_type], 'values':values, 'labels':field_labels(form_type),
        'title':'Account Application' if form_type=='new_account' else 'Information Change'},
        on_edit_change=on_edit)
