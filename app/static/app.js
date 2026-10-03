const $ = (s) => document.querySelector(s);
const urlInput = $('#url');
let selectedFormat = 'mp4';

$('.segmented').addEventListener('click', (e) => {
  const btn = e.target.closest('.segment');
  if (!btn) return;
  document.querySelectorAll('.segment').forEach(x => x.classList.remove('active'));
  btn.classList.add('active');
  selectedFormat = btn.dataset.format;
});

$('#pasteBtn').addEventListener('click', async () => {
  try {
    urlInput.value = await navigator.clipboard.readText();
    urlInput.focus();
  } catch {
    showError('Clipboard tidak bisa diakses browser ini. Paste manual link-nya.');
  }
});

function showError(msg){
  $('#error').textContent = msg;
  $('#error').classList.remove('hidden');
}
function clearMessages(){ $('#error').classList.add('hidden'); $('#result').classList.add('hidden'); }
function esc(v){ return String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }

function platformLabel(p){ return ({tiktok:'TikTok',instagram:'Instagram',facebook:'Facebook',pinterest:'Pinterest'})[p] || p; }

$('#inspectBtn').addEventListener('click', async () => {
  const url = urlInput.value.trim();
  clearMessages();
  if (!url) return showError('Masukkan URL terlebih dahulu.');
  const btn = $('#inspectBtn');
  btn.disabled = true; btn.innerHTML = 'READING…';
  try {
    const r = await fetch('/api/resolve', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})});
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'URL gagal diproses.');
    const d = data.data;
    const kind = d.kind === 'slideshow' ? `PHOTO SLIDESHOW${d.image_count ? ` • ${d.image_count} IMAGES` : ''}` : (d.kind || 'MEDIA').toUpperCase();
    $('#result').innerHTML = `
      <div class="result-grid">
        <img class="thumb" src="${esc(d.thumbnail || '/favicon.svg')}" onerror="this.src='/favicon.svg'" alt="thumbnail">
        <div class="meta">
          <h4>${esc(d.title || 'Untitled')}</h4>
          <p>${esc(platformLabel(data.platform))} • ${esc(kind)}</p>
          ${d.author ? `<p>by ${esc(d.author)}</p>` : ''}
          <p>Pilih <b>${selectedFormat.toUpperCase()}</b>, lalu klik download.</p>
        </div>
        <button class="download-btn" id="downloadBtn">DOWNLOAD ${selectedFormat.toUpperCase()}</button>
      </div>`;
    $('#result').classList.remove('hidden');
    $('#downloadBtn').addEventListener('click', () => doDownload(url));
  } catch (err) {
    showError(err.message || 'Terjadi kesalahan.');
  } finally {
    btn.disabled = false; btn.innerHTML = 'INSPECT <span>→</span>';
  }
});

async function doDownload(url){
  const b = $('#downloadBtn');
  b.disabled = true; b.textContent = 'PROCESSING…';
  try {
    const r = await fetch('/api/download', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url, format:selectedFormat})});
    if (!r.ok){
      const j = await r.json().catch(()=>({}));
      throw new Error(j.detail || 'Download gagal.');
    }
    const blob = await r.blob();
    const cd = r.headers.get('content-disposition') || '';
    const match = cd.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : `z-downloder.${selectedFormat}`;
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    b.textContent = 'DOWNLOADED ✓';
  } catch(err) {
    showError(err.message || 'Download gagal.');
    b.textContent = `DOWNLOAD ${selectedFormat.toUpperCase()}`;
  } finally { b.disabled = false; }
}

urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') $('#inspectBtn').click(); });
