/* STOP SERVER button for the dashboard. Asks the PDF Scope control helper
   (127.0.0.1:8100) to stop the PDF server. Your files stay in the workspace. */
(() => {
  const HELPER = 'http://127.0.0.1:8100';
  const btn = document.getElementById('stopBtn');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    if (!confirm('Stop the PDF server? Your files stay in the workspace.')) return;
    try {
      const r = await fetch(HELPER + '/api/stop', { method: 'POST' });
      const j = await r.json();
      if (!j.ok) throw new Error(j.message);
      showStopped();
    } catch (e) {
      alert('Could not reach the PDF Scope control helper, so the server was not stopped.\n\n' +
            'Open "Start PDF Scope" from the project folder to manage it.');
    }
  });

  function showStopped() {
    const led = document.getElementById('srvLed');
    const txt = document.getElementById('srvTxt');
    if (led) led.className = 'led bad';
    if (txt) txt.textContent = 'STOPPED';
    const o = document.createElement('div');
    o.id = 'stoppedOverlay';
    o.innerHTML = '<div class="so-box"><b>SERVER STOPPED</b>' +
      '<p>Your files are still in the workspace. Double-click <i>Start PDF Scope</i> in the project folder to start it again.</p></div>';
    document.body.appendChild(o);
  }
})();
