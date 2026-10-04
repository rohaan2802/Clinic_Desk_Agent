const $=id=>document.getElementById(id);
let session=crypto.randomUUID(),count=0,busy=false;

const MODEL_LABELS={
  'clinic-policy-v1':'Built-in clinic policy (fast)',
  'gemini-3.8-flash':'Gemini 3.8 Flash',
  'gemini-3.5-flash-lite':'Gemini 3.5 Flash Lite',
  'openai/gpt-4o-mini':'OpenRouter GPT-4o mini'
};

const STATUS_LABELS={
  completed:'Done',
  needs_clarification:'Need a bit more info',
  blocked:'I cannot do that',
  approval_required:'Needs staff approval',
  tool_error:'Lookup failed',
  contract_error:'Could not finish',
  budget_exceeded:'Ran out of steps',
  failed:'Something went wrong'
};

const TOOL_LABELS={
  search_availability:'Looked up open times',
  list_appointments:'Listed visits',
  book_appointment:'Booked a visit',
  cancel_appointment:'Tried to cancel a visit',
  reschedule_appointment:'Tried to move a visit'
};

const OUTCOME_LABELS={
  success:'worked',
  timeout:'needed a retry',
  malformed_output:'needed a retry',
  rejected:'was not allowed',
  exception:'had a problem'
};

const EVENT_LABELS={
  run_start:'Started your request',
  untrusted_instruction_ignored:'Ignored a rule-breaking note',
  model_decision:'Chose the next step',
  fault_injected:'Practiced a fault, then recovered',
  model_fallback:'Switched to the built-in clinic policy',
  repair:'Fixed a bad step and continued',
  tool_result:'Finished a clinic action',
  agent_stop:'Stopped',
  false_block_overridden:'Corrected a wrong block'
};

function bubble(role,text){
  const article=document.createElement('article');
  article.className='bubble '+role;
  const who=document.createElement('span');
  who.className='who';
  who.textContent=role==='user'?'You':'ClinicDesk';
  article.append(who,document.createTextNode(text));
  $('messages').append(article);
  $('messages').scrollTop=$('messages').scrollHeight;
}

function setStatus(text,mode){
  $('status').textContent=text;
  $('status').className='status-pill '+(mode||'');
}

function setBusy(on){
  busy=on;
  $('send').disabled=on;
  $('reset').disabled=on;
  const side=$('reset-side');
  if(side)side.disabled=on;
  $('task').disabled=on;
  $('external').disabled=on;
  $('model').disabled=on;
  document.querySelectorAll('#examples button').forEach(button=>{button.disabled=on});
}

function friendlyStatus(data){
  const label=STATUS_LABELS[data.status]||data.status;
  const steps=data.steps===1?'1 step':data.steps+' steps';
  return label+' · '+steps;
}

function friendlyTools(calls){
  if(!calls||!calls.length)return 'I did not need a clinic action for this message.';
  return calls.map(call=>{
    const name=TOOL_LABELS[call.tool]||call.tool;
    const outcome=OUTCOME_LABELS[call.outcome]||call.outcome;
    return '• '+name+' — '+outcome;
  }).join('\n');
}

function friendlyEvents(events){
  if(!events||!events.length)return 'No extra notes for this message.';
  return events.map(event=>{
    const label=EVENT_LABELS[event.event]||'Update';
    return '• '+label;
  }).join('\n');
}

async function ping(){
  try{
    const r=await fetch('/health');
    const data=await r.json();
    $('live').textContent=data.status==='ok'?'live · ClinicDesk':'down';
    $('live').classList.toggle('ok',data.status==='ok');
  }catch{
    $('live').textContent='offline';
    $('live').classList.remove('ok');
  }
}

async function loadModels(tries=12){
  for(let i=0;i<tries;i++){
    try{
      const r=await fetch('/models');
      if(!r.ok)throw Error('bad status');
      const data=await r.json();
      const select=$('model');
      select.replaceChildren();
      for(const name of data.models){
        if(name==='unconfigured')continue;
        const option=document.createElement('option');
        option.value=name;
        option.textContent=MODEL_LABELS[name]||name;
        select.append(option);
      }
      if(select.options.length){
        setStatus('Ready');
        $('send').disabled=false;
        return true;
      }
    }catch{
      setStatus('Starting ClinicDesk…','busy');
      await new Promise(resolve=>setTimeout(resolve,400));
    }
  }
  setStatus('Could not load answer options. Refresh once.','busy');
  $('send').disabled=true;
  return false;
}

async function init(){
  if(history.scrollRestoration)history.scrollRestoration='manual';
  window.scrollTo(0,0);
  setStatus('Starting ClinicDesk…','busy');
  await loadModels();
  await ping();
  if(!$('messages').children.length){
    bubble('agent','Hi. I can find open times, book a visit, show a student’s visits, cancel, or move a visit. Use a chip below, or type something like “Book a general visit tomorrow morning for student S-1001”.');
  }
  window.scrollTo(0,0);
}

document.querySelectorAll('#examples button').forEach(button=>{
  button.onclick=()=>{
    if(busy)return;
    $('task').value=button.dataset.task;
    $('task').focus();
    button.animate([{transform:'scale(.96)'},{transform:'scale(1)'}],{duration:180});
  };
});

$('task').addEventListener('keydown',event=>{
  if(event.key==='Enter'&&!event.shiftKey){
    event.preventDefault();
    if(busy)return;
    $('chat').requestSubmit();
  }
});

function isSlowModel(name){
  return name && name!=='clinic-policy-v1' && name!=='unconfigured';
}

function showThinking(on){
  const el=$('thinking');
  if(!el)return;
  el.hidden=!on;
  if(on)$('messages').scrollTop=$('messages').scrollHeight;
}

$('chat').onsubmit=async event=>{
  event.preventDefault();
  if(busy)return;
  const task=$('task').value.trim();
  if(!task)return;
  const note=$('external').value.trim();
  const model=$('model').value;
  $('task').value='';
  bubble('user',task);
  setBusy(true);
  if(isSlowModel(model)){
    showThinking(true);
    setStatus('Thinking…','busy');
    $('trace').textContent='Waiting for the model…';
    $('observations').textContent='Thinking…';
  }else{
    showThinking(false);
    setStatus('Working on it…','busy');
    $('trace').textContent='Checking the clinic records…';
    $('observations').textContent='Waiting for the result…';
  }
  try{
    const response=await fetch('/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        session_id:session,
        task,
        model,
        external_context:note?[{source:'browser-note',content:note,trust:'untrusted'}]:[]
      })
    });
    const data=await response.json();
    if(!response.ok)throw Error('The desk could not take that request. Please try again.');
    bubble('agent',data.final_response);
    count+=2;
    $('memory').textContent=count+' messages in this chat · I keep the last 100 turns';
    setStatus(friendlyStatus(data),'done');
    $('trace').textContent=friendlyTools(data.tool_calls);
    $('observations').textContent=friendlyEvents(data.events);
  }catch(error){
    setStatus(error.message,'busy');
  }finally{
    showThinking(false);
    setBusy(false);
  }
};

async function clearChat(){
  if(busy)return;
  try{
    setBusy(true);
    const response=await fetch('/chat/'+session,{method:'DELETE'});
    if(!response.ok)throw Error('I could not clear this chat.');
    session=crypto.randomUUID();
    count=0;
    $('messages').replaceChildren();
    bubble('agent','Cleared. How can I help with a practice clinic visit?');
    showThinking(false);
    $('memory').textContent='No messages yet in this chat';
    $('external').value='';
    $('task').value='';
    setStatus('Ready');
    $('trace').textContent='Nothing yet. Send a request to begin.';
    $('observations').textContent='Waiting for your first message.';
  }catch(error){
    setStatus(error.message,'busy');
  }finally{
    setBusy(false);
  }
}

$('reset').onclick=clearChat;
const resetSide=$('reset-side');
if(resetSide)resetSide.onclick=clearChat;

init();
setInterval(ping,15000);
