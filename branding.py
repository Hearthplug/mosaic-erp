"""Safe tenant theme generation from interview answers."""
import re
DEFAULT={'primary':'#175b4d','accent':'#f2a93b','surface':'#ffffff','text':'#17201e'}
def theme(model):
 b=model['settings']['branding']['value'];colors=re.findall(r'#[0-9a-fA-F]{6}',b.get('colors') or '')[:2];out=dict(DEFAULT)
 if colors:out['primary']=colors[0]
 if len(colors)>1:out['accent']=colors[1]
 out.update({'style':b.get('style'),'logo_status':'pending_upload' if b.get('logo','').startswith('Yes') else 'text_only','css_variables':{f'--brand-{k}':v for k,v in out.items() if k in ('primary','accent','surface','text')}})
 return out
