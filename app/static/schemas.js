const FIELD_LABELS={
  arena_version:'Arena version',
  request_id:'Request id',
  task:'Task',
  external_context:'Extra notes',
  arena_config:'Run settings',
  session_id:'Chat session id',
  model:'Answer model',
  status:'Status',
  final_response:'Final reply',
  steps:'Steps used',
  stop_reason:'Stop reason',
  tool_calls:'Tool calls',
  errors:'Errors',
  events:'Events',
  metrics:'Metrics',
  max_steps:'Maximum steps',
  fault:'Practice fault',
  type:'Fault type',
  trigger:'Fault trigger',
  source:'Note source',
  content:'Note text',
  trust:'Trust level',
  step:'Step number',
  tool:'Tool name',
  attempt:'Attempt number',
  outcome:'Outcome',
  latency_ms:'Time taken (milliseconds)',
  model_calls:'Model calls',
  input_tokens:'Input tokens',
  output_tokens:'Output tokens',
  estimated_cost_usd:'Estimated cost (US dollars)',
  loc:'Location of the problem',
  msg:'Error message',
  input:'Invalid value you sent',
  ctx:'Extra error details',
  detail:'Error details'
};

const SCHEMA_TITLES={
  ArenaRequest:'Arena request',
  ChatRequest:'Chat request',
  ArenaResponse:'Arena response',
  ArenaConfig:'Run settings',
  Fault:'Practice fault',
  ExternalContext:'Extra note',
  ToolTrace:'Tool call record',
  Metrics:'Run metrics',
  HTTPValidationError:'Request validation error',
  ValidationError:'Field validation error'
};

function friendlyName(name){
  return FIELD_LABELS[name]||name.replaceAll('_',' ');
}

function schemaRef(value){
  return (value && value.$ref || '').split('/').pop();
}

function schemaType(value){
  if(!value)return 'Any value';
  if(value.$ref)return SCHEMA_TITLES[schemaRef(value)]||schemaRef(value);
  if(value.anyOf)return value.anyOf.map(schemaType).filter((item,index,list)=>list.indexOf(item)===index).join(' or ');
  if(value.enum)return value.enum.join('  |  ');
  if(value.type==='array')return 'List of ' + schemaType(value.items || {});
  const names={string:'Text',integer:'Number',number:'Number',boolean:'Yes / No',object:'Object',null:'Empty'};
  return names[value.type] || value.type || 'Any value';
}

function schemaNote(value){
  const bits=[];
  if(!value)return '';
  if(value.description)bits.push(String(value.description).replace(/\.$/,''));
  if(value.minLength!=null||value.maxLength!=null){
    bits.push((value.minLength||0)+' to '+(value.maxLength||'many')+' characters');
  }
  if(value.minimum!=null&&value.maximum!=null){
    bits.push('range '+value.minimum+' to '+value.maximum);
  }else if(value.minimum!=null){
    bits.push(value.minimum+' or more');
  }else if(value.maximum!=null){
    bits.push('up to '+value.maximum);
  }
  if(value.maxItems!=null)bits.push('up to '+value.maxItems+' items');
  if(value.const!=null)bits.push('always '+value.const);
  return bits.join('. ');
}

function fieldCard(name, value, required){
  const type=schemaType(value);
  const note=schemaNote(value);
  const need=required?'Required':'Optional';
  return (
    '<div class="schema-field">'+
      '<p class="schema-name">'+friendlyName(name)+'</p>'+
      '<p class="schema-type">'+type+'</p>'+
      '<p class="schema-need">'+need+'</p>'+
      (note?'<p class="schema-note">'+note+'</p>':'')+
    '</div>'
  );
}

function schemaCard(name, schema){
  const required=new Set(schema.required||[]);
  const props=schema.properties||{};
  const fields=Object.keys(props).length
    ? Object.entries(props).map(([key,value])=>fieldCard(key,value,required.has(key))).join('')
    : '<p class="schema-note">No fields on this object.</p>';
  const title=SCHEMA_TITLES[name]||name;
  return (
    '<article class="schema-card">'+
      '<button type="button" class="schema-toggle" aria-expanded="false">'+
        '<span class="schema-title">'+title+'</span>'+
        '<span class="schema-arrow" aria-hidden="true">▲</span>'+
      '</button>'+
      '<div class="schema-body" hidden>'+
        (schema.description?'<p class="schema-lead">'+schema.description+'</p>':'')+
        fields+
      '</div>'+
    '</article>'
  );
}

function closeCard(card){
  card.classList.remove('is-open');
  const toggle=card.querySelector('.schema-toggle');
  const body=card.querySelector('.schema-body');
  if(toggle)toggle.setAttribute('aria-expanded','false');
  if(body)body.hidden=true;
}

function openCard(card){
  card.classList.add('is-open');
  const toggle=card.querySelector('.schema-toggle');
  const body=card.querySelector('.schema-body');
  if(toggle)toggle.setAttribute('aria-expanded','true');
  if(body)body.hidden=false;
}

fetch('/openapi-spec').then(r=>r.json()).then(spec=>{
  const schemas=(spec.components&&spec.components.schemas)||{};
  const root=document.getElementById('schema-cards');
  if(!root)return;
  const order=['ArenaRequest','ChatRequest','ArenaResponse','ArenaConfig','Fault','ExternalContext','ToolTrace','Metrics'];
  const names=[...order.filter(name=>schemas[name]),...Object.keys(schemas).filter(name=>!order.includes(name))];
  root.innerHTML=names.map(name=>schemaCard(name,schemas[name])).join('');
  root.addEventListener('click',event=>{
    const toggle=event.target.closest('.schema-toggle');
    if(!toggle)return;
    const card=toggle.closest('.schema-card');
    const wasOpen=card.classList.contains('is-open');
    root.querySelectorAll('.schema-card.is-open').forEach(closeCard);
    if(typeof window.closeAllSwaggerCards==='function')window.closeAllSwaggerCards();
    if(!wasOpen)openCard(card);
  });
}).catch(()=>{
  const root=document.getElementById('schema-cards');
  if(root)root.innerHTML='<p class="schema-note">Could not load the field list.</p>';
});
