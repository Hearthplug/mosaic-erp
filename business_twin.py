"""Explainable consequence preview for interview-derived operating models."""
def preview(model,scenario):
 s=model['settings'];kind=scenario['kind'];effects=[];blocks=[]
 if kind=='sale':
  effects=['Reduce stock','Record customer payment or amount owed','Post sales, tax and cost entries','Update daily sales and cash views']
  if scenario.get('payment')=='later' and not s['credit']['value']['enabled']:blocks.append('You said customers pay immediately. Confirm whether customer credit really happens before this can post.')
 if kind=='refund':effects=['Require the configured approval','Record the refund','Decide whether goods return to stock','Reverse sales, tax and cost entries']
 if kind=='rule_change':effects=['Create a new effective operating-model version','Show changed screens and permissions','Keep old transactions on their original rule version','Send finance, tax or legal changes for re-verification']
 return {'scenario':kind,'effects':effects,'blocks':blocks,'post_allowed':not blocks,'explanation':'This is a preview. Nothing is posted until the owner approves the complete action.'}
