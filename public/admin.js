async function req(url, options={}) { const r=await fetch(url,{credentials:"same-origin",...options}); const d=await r.json(); if(!r.ok) throw Error(d.error||"Request failed"); return d; }
async function login(){try{await req("/api/admin/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:username.value,password:password.value})}); await boot();}catch(e){loginMsg.textContent=e.message;}}
async function boot(){await req("/api/admin/me").then(d=>{loginBox.hidden=d.ok;dashboard.hidden=!d.ok;});if(!dashboard.hidden){loadNumbers();loadKeys();loadDeleted();}}
async function addNumber(){try{await req("/api/admin/numbers",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({country_code:cc.value,phone:phone.value})});phone.value="";loadNumbers();}catch(e){alert(e.message);}}
async function bulkPasteImport(){
  const raw = bulkPaste.value.trim();
  if(!raw){pasteMsg.textContent="Paste at least one number.";return;}
  const lines = raw.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  const records = [];
  let invalid = 0;
  for(const line of lines){
    if(/^country_code\s*,\s*phone$/i.test(line)) continue;
    const parts = line.split(",").map(x=>x.trim());
    if(parts.length !== 2){invalid++;continue;}
    const cc = parts[0] || "+91";
    const phone = parts[1].replace(/\s+/g,"");
    if(!/^\+[1-9]\d{0,3}$/.test(cc) || !/^\d{5,15}$/.test(phone)){invalid++;continue;}
    records.push({country_code:cc,phone});
  }
  if(!records.length){pasteMsg.textContent=`No valid rows. Invalid: ${invalid}`;return;}
  const csvText = "country_code,phone\n" + records.map(x=>`${x.country_code},${x.phone}`).join("\n");
  const fd = new FormData();
  fd.append("file",new Blob([csvText],{type:"text/csv"}),"bulk-paste.csv");
  try{
    const d = await req("/api/admin/numbers/bulk",{method:"POST",body:fd});
    pasteMsg.textContent=`Added: ${d.added} · Duplicate/invalid on server: ${d.skipped} · Invalid pasted rows: ${invalid}`;
    bulkPaste.value="";
    loadNumbers();
  }catch(e){pasteMsg.textContent=e.message;}
}
async function bulkImport(){try{const f=csv.files[0];if(!f)throw Error("Choose CSV");const fd=new FormData();fd.append("file",f);const d=await req("/api/admin/numbers/bulk",{method:"POST",body:fd});bulkMsg.textContent=`Added ${d.added}; skipped ${d.skipped}`;loadNumbers();}catch(e){bulkMsg.textContent=e.message;}}
async function loadNumbers(){try{const d=await req("/api/admin/numbers");numbers.innerHTML=d.numbers.map(n=>`<div class="number-row"><label><input class="number-check" type="checkbox" value="${n.id}" onchange="updateSelectedCount()"> <span>${n.country_code} ${n.phone} · ${n.status}</span></label><button class="danger" onclick="deleteNumber('${n.id}')">Delete</button></div>`).join("")||"No numbers";updateSelectedCount();}catch(e){numbers.textContent=e.message;}}
function selectedNumbers(){const ids=new Set([...document.querySelectorAll('.number-check:checked')].map(x=>x.value));return [...document.querySelectorAll('.number-check')].filter(x=>ids.has(x.value)).map(x=>x.closest('.number-row').querySelector('span').textContent.trim());}
function updateSelectedCount(){const n=document.querySelectorAll('.number-check:checked').length;selectedCount.textContent=`${n} selected · Export contains phone numbers only`;}
function toggleAll(checked){document.querySelectorAll('.number-check').forEach(x=>x.checked=checked);updateSelectedCount();}
function exportSelected(){const rows=[...document.querySelectorAll('.number-check:checked')].map(x=>x.closest('.number-row').querySelector('span').textContent.trim());if(!rows.length){alert('Select at least one number');return;}const csv='country_and_phone\n'+rows.map(x=>'"'+x.replaceAll('"','""')+'"').join('\n');const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='numberhub-selected-numbers.csv';a.click();URL.revokeObjectURL(a.href);}
async function deleteNumber(id){if(!confirm("Move this number to Deleted History?"))return;await req("/api/admin/numbers/"+id,{method:"DELETE"});loadNumbers();loadDeleted();}
async function loadDeleted(){try{const d=await req('/api/admin/deleted');deletedNumbers.innerHTML=d.numbers.map(n=>`<div class="number-row"><span>${n.country_code} ${n.phone} · ${n.deleted_at} · ${n.reason}</span><b>Deleted</b></div>`).join('')||'No deleted numbers';}catch(e){deletedNumbers.textContent=e.message;}}
async function createKey(){try{const d=await req("/api/admin/keys",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({label:label.value||"Customer"})});newKey.textContent=d.api_key+"\nCopy it now; it will not be shown again.";loadKeys();}catch(e){alert(e.message);}}
async function loadKeys(){try{const d=await req("/api/admin/keys");keys.innerHTML=d.keys.map(k=>`<p>${k.label||"Customer"} · ${k.active?"Active":"Revoked"} ${k.active?`<button class="danger" onclick="revokeKey('${k.id}')">Revoke</button>`:""}</p>`).join("")||"No keys";}catch(e){keys.textContent=e.message;}}
async function revokeKey(id){await req("/api/admin/keys/"+id,{method:"PATCH"});loadKeys();}
async function logout(){await req("/api/admin/logout",{method:"POST"});boot();}
boot().catch(()=>{});

async function bulkOtpPaste(){const text=otpPaste.value.trim();if(!text){otpPasteMsg.textContent="Paste CSV rows first.";return;}try{const fd=new FormData();fd.append("text",text);const d=await req("/api/admin/otps/bulk",{method:"POST",body:fd});otpPasteMsg.textContent=`Attached: ${d.added} · Skipped: ${d.skipped} · Expires in 5 minutes`;otpPaste.value="";}catch(e){otpPasteMsg.textContent=e.message;}}
async function bulkOtpCsv(){const f=otpCsv.files[0];if(!f){otpCsvMsg.textContent="Choose a CSV file.";return;}try{const fd=new FormData();fd.append("file",f);const d=await req("/api/admin/otps/bulk",{method:"POST",body:fd});otpCsvMsg.textContent=`Attached: ${d.added} · Skipped: ${d.skipped} · Expires in 5 minutes`;otpCsv.value="";}catch(e){otpCsvMsg.textContent=e.message;}}
