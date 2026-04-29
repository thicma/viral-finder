// ── Tab Navigation ─────────────────────────────────────────────
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`tab-${tab}`).classList.add('active');
    });
});

// ── TAB 1: Viral Search ────────────────────────────────────────
const searchForm    = document.getElementById('search-form');
const searchResults = document.getElementById('search-results');
const searchEmpty   = document.getElementById('search-empty');
const searchBtn     = document.getElementById('search-btn');
const searchSpinner = document.getElementById('search-spinner');
const resultInfo    = document.getElementById('result-info');
const cardTpl       = document.getElementById('card-tpl');
let   activeHours   = 0;      // 0 = all time
let   allResults    = [];     // full cached result set from last fetch
let   outlierMode   = false;  // 🔬 channel outlier mode

// ── Period pills: filter client-side from cache ──
document.querySelectorAll('.filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
        document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        activeHours = parseInt(pill.dataset.hours);
        if (allResults.length > 0) renderResults(allResults); // instant, no fetch
    });
});

// ── Outlier Mode toggle ──
const outlierToggle = document.getElementById('outlier-toggle');
outlierToggle.addEventListener('click', () => {
    outlierMode = !outlierMode;
    outlierToggle.classList.toggle('active', outlierMode);
    outlierToggle.querySelector('.toggle-state').textContent = outlierMode ? 'ON' : 'OFF';
    // Clear cache so next search uses the right endpoint
    allResults = [];
    searchResults.innerHTML = '';
    resultInfo.classList.add('hidden');
});

// ── Search: always fetch ALL time, cache everything ──
searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const keyword = document.getElementById('keyword').value.trim();
    if (!keyword) return;

    setLoading(searchBtn, searchSpinner, true);
    searchResults.innerHTML = '';
    searchEmpty.classList.add('hidden');
    resultInfo.classList.add('hidden');
    allResults = [];

    try {
        const endpoint = outlierMode ? '/api/channel-outliers' : '/api/search';
        if (outlierMode) {
            setLoadingText(searchBtn, '🔬 Fetching + analyzing channels...');
        }
        const res  = await fetch(endpoint, {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({keyword, max_hours: 0})
        });
        const data = await res.json();
        if (data.results && data.results.length > 0) {
            allResults = data.results; // cache
            renderResults(allResults);
        } else {
            searchEmpty.classList.remove('hidden');
        }
    } catch {
        searchEmpty.classList.remove('hidden');
    } finally {
        setLoading(searchBtn, searchSpinner, false, 'Search Virals');
    }
});

function renderResults(all) {
    // Filter by active period client-side
    const filtered = activeHours === 0
        ? all
        : all.filter(v => v.hours <= activeHours);

    searchResults.innerHTML = '';
    searchEmpty.classList.add('hidden');
    resultInfo.classList.add('hidden');

    if (filtered.length === 0) {
        searchEmpty.classList.remove('hidden');
        return;
    }

    const periodLabel = document.querySelector('.filter-pill.active')?.textContent?.trim() || 'All time';
    resultInfo.innerHTML =
        '<span>🎯 <strong>' + filtered.length + '</strong> of ' + all.length + ' titles shown</span>' +
        '<span class="info-sep">·</span>' +
        '<span>Period: <strong>' + periodLabel + '</strong></span>' +
        '<span class="info-sep">·</span>' +
        '<span>Sorted by <strong>Outlier Score</strong> (views ÷ √hours)</span>';
    resultInfo.classList.remove('hidden');

    filtered.forEach(v => {
        const clone = cardTpl.content.cloneNode(true);
        clone.querySelector('.rc-img').src = v.thumbnail;

        const badge = clone.querySelector('.rc-badge');

        if (outlierMode && v.ratio > 0) {
            // Outlier mode: show Views/Subscribers ratio
            badge.innerHTML = v.tier + ' <span class="rc-vph">' + v.ratio + 'x</span>';
            badge.title = v.views_str + ' views · ' + v.subs_str + ' subscribers';
            if (v.ratio >= 20)     { badge.style.color = '#f59e0b'; badge.style.borderColor = 'rgba(245,158,11,.4)'; }
            else if (v.ratio >= 10){ badge.style.color = '#ef4444'; badge.style.borderColor = 'rgba(239,68,68,.4)'; }
            else if (v.ratio >= 3) { badge.style.color = '#10b981'; badge.style.borderColor = 'rgba(16,185,129,.4)'; }
            else                   { badge.style.color = '#60a5fa'; }

            // Add subscriber count below channel name
            const channelEl = clone.querySelector('.rc-channel');
            channelEl.textContent = v.channel + ' · ' + v.subs_str + ' subs';
        } else {
            badge.innerHTML = '<span class="rc-vph">' + v.outlier.toLocaleString('en-US') + '</span> Score';
            if (v.outlier > 5000)      badge.style.color = '#f59e0b';
            else if (v.outlier > 1000) badge.style.color = '#10b981';
            else                       badge.style.color = '#60a5fa';
            clone.querySelector('.rc-channel').textContent = v.channel;
        }
        clone.querySelector('.rc-views').textContent = v.views_str;
        clone.querySelector('.rc-pub').textContent = v.published + ' (' + v.vph + ' VPH)';
        clone.querySelector('.rc-link').href = v.url;
        searchResults.appendChild(clone);
    });

    // Auto-populate preview decoys with real search results
    populatePreviewDecoys(filtered);
    showPreviewToast(filtered.length);
}

// ── Populate preview decoys with real videos from search ────────
function populatePreviewDecoys(videos) {
    if (!videos || videos.length === 0) return;

    // Shuffle for variety
    const pool = [...videos].sort(() => Math.random() - 0.5);
    let idx = 0;
    const next = () => pool[idx++ % pool.length];

    // ── Home grid decoys ──
    document.querySelectorAll('.yt-card.decoy').forEach(card => {
        const v = next();
        card.innerHTML =
            '<div class="yt-card-thumb" style="position:relative;border-radius:8px;overflow:hidden;background:#1a1a1a;aspect-ratio:16/9">' +
                '<img src="' + v.thumbnail + '" style="width:100%;height:100%;object-fit:cover" loading="lazy">' +
            '</div>' +
            '<div class="yt-card-meta" style="display:flex;gap:.6rem;margin-top:.6rem;align-items:flex-start">' +
                '<div class="yt-avatar-dot"></div>' +
                '<div class="yt-meta-lines">' +
                    '<div class="yt-title">' + escHtml(v.title) + '</div>' +
                    '<div class="yt-channel">' + escHtml(v.channel) + '</div>' +
                    '<div class="yt-views">' + escHtml(v.views_str) + '</div>' +
                '</div>' +
            '</div>';
    });

    // ── Suggested sidebar decoys ──
    document.querySelectorAll('.decoy-sug').forEach(item => {
        const v = next();
        item.innerHTML =
            '<div class="sug-thumb" style="width:168px;height:94px;flex-shrink:0;border-radius:6px;overflow:hidden;background:#1a1a1a">' +
                '<img src="' + v.thumbnail + '" style="width:100%;height:100%;object-fit:cover" loading="lazy">' +
            '</div>' +
            '<div class="sug-meta">' +
                '<div class="yt-title small-title">' + escHtml(v.title) + '</div>' +
                '<div class="yt-channel sug-channel">' + escHtml(v.channel) + '</div>' +
                '<div class="yt-views sug-views">' + escHtml(v.views_str) + '</div>' +
            '</div>';
    });

    // ── Mobile feed decoys ──
    document.querySelectorAll('.decoy-mob').forEach(card => {
        const v = next();
        card.innerHTML =
            '<div class="mob-thumb" style="aspect-ratio:16/9;overflow:hidden;background:#1a1a1a">' +
                '<img src="' + v.thumbnail + '" style="width:100%;height:100%;object-fit:cover" loading="lazy">' +
            '</div>' +
            '<div class="mob-card-meta" style="display:flex;gap:.6rem;align-items:flex-start;padding:.5rem .75rem">' +
                '<div class="mob-avatar-dot"></div>' +
                '<div class="mob-lines">' +
                    '<div class="mob-title">' + escHtml(v.title) + '</div>' +
                    '<div class="mob-sub">' + escHtml(v.channel) + ' · ' + escHtml(v.views_str) + '</div>' +
                '</div>' +
            '</div>';
    });
}

function escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showPreviewToast(count) {
    let toast = document.getElementById('preview-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'preview-toast';
        toast.className = 'preview-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = '🖼️ Thumbnail Preview updated with ' + count + ' real videos from your search';
    toast.classList.add('toast-visible');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('toast-visible'), 3500);
}

// ── TAB 2: Script Analyzer ─────────────────────────────────────
const analyzeBtn     = document.getElementById('analyze-btn');
const analyzeSpinner = document.getElementById('analyze-spinner');
const analyzerOutput = document.getElementById('analyzer-output');
const titleTpl       = document.getElementById('title-tpl');
let   lastAnalysis   = null; // stores last API result for download
const TRIGGER_COLORS = {
    curiosity:   '#f59e0b',
    fear:        '#ef4444',
    aspiration:  '#6366f1',
    relief:      '#10b981',
    'social proof': '#ec4899',
    controversy: '#f97316',
    motivation:  '#8b5cf6',
};

analyzeBtn.addEventListener('click', async () => {
    const script = document.getElementById('script-input').value.trim();
    const niche  = document.getElementById('niche-input').value.trim();
    if (!script) { alert('Please paste your script first.'); return; }

    setLoading(analyzeBtn, analyzeSpinner, true);
    analyzerOutput.innerHTML = '<div class="output-placeholder glass"><span style="font-size:2rem">⏳</span><p>Analyzing your script...</p></div>';

    try {
        const res  = await fetch('/api/analyze', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({script, niche})
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        analyzerOutput.innerHTML = '';

        // Topic summary card
        const topicDiv = document.createElement('div');
        topicDiv.className = 'topic-card fade-in';
        topicDiv.innerHTML = `
            <div class="topic-label">Core Topic</div>
            <div class="topic-text">${data.core_topic || ''}</div>
            <div class="topic-label" style="margin-top:.75rem">Viewer Pain / Desire</div>
            <div class="topic-text">${data.avatar_pain || ''}</div>
        `;
        analyzerOutput.appendChild(topicDiv);

        // Title cards
        (data.titles || []).forEach(t => {
            const clone = titleTpl.content.cloneNode(true);
            const score = t.hook_score || 0;
            const trigger = (t.emotional_trigger || '').toLowerCase();
            const color = TRIGGER_COLORS[trigger] || '#888';

            clone.querySelector('.tc-score').textContent = `${score}/10`;
            clone.querySelector('.tc-score').style.color = scoreColor(score);
            clone.querySelector('.tc-trigger-badge').textContent = t.emotional_trigger;
            clone.querySelector('.tc-trigger-badge').style.color = color;
            clone.querySelector('.tc-trigger-badge').style.background = color + '18';
            clone.querySelector('.tc-trigger-badge').style.borderColor = color + '40';
            clone.querySelector('.tc-title').textContent = t.title;
            clone.querySelector('.tc-formula').textContent = t.formula;
            clone.querySelector('.tc-why').textContent = t.why_it_works;
            // Thumb text suggestion
            const thumbEl = clone.querySelector('.tc-thumb-text');
            if (thumbEl && t.thumb_text) {
                thumbEl.textContent = '\uD83D\uDDBC\uFE0F ' + t.thumb_text;
                thumbEl.classList.remove('hidden');
            }
            analyzerOutput.appendChild(clone);
        });

        // Save for download & show button
        lastAnalysis = data;
        showDownloadBtn();

    } catch (err) {
        analyzerOutput.innerHTML = `<div class="output-placeholder glass"><span style="font-size:2rem">❌</span><p>Error: ${err.message}</p></div>`;
    } finally {
        setLoading(analyzeBtn, analyzeSpinner, false, '✨ Analyze Script');
    }
});

function showDownloadBtn() {
    let existing = document.getElementById('download-btn');
    if (existing) return; // already shown
    const btn = document.createElement('button');
    btn.id = 'download-btn';
    btn.className = 'btn-primary full-width';
    btn.style.marginTop = '1rem';
    btn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
    btn.innerHTML = '⬇️ Download Titles (.txt)';
    btn.addEventListener('click', downloadTitles);
    // Insert after the analyze button's parent column
    document.querySelector('.analyzer-input-col').appendChild(btn);
}

function downloadTitles() {
    if (!lastAnalysis) return;
    const d = lastAnalysis;
    const lines = [];
    lines.push('VIRAL TITLE ANALYSIS');
    lines.push('Generated by ViralFinder · ' + new Date().toLocaleString());
    lines.push('='.repeat(60));
    lines.push('');
    lines.push('CORE TOPIC');
    lines.push(d.core_topic || '');
    lines.push('');
    lines.push('VIEWER PAIN / DESIRE');
    lines.push(d.avatar_pain || '');
    lines.push('');
    lines.push('='.repeat(60));
    lines.push('VIRAL TITLES');
    lines.push('='.repeat(60));
    lines.push('');
    (d.titles || []).forEach((t, i) => {
        lines.push(`[${i + 1}] ${t.title}`);
        lines.push(`    Hook Score   : ${t.hook_score}/10`);
        lines.push(`    Formula      : ${t.formula}`);
        lines.push(`    Trigger      : ${t.emotional_trigger}`);
        lines.push(`    Thumb Text   : ${t.thumb_text || '—'}`);
        lines.push(`    Why it works : ${t.why_it_works}`);
        lines.push('');
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = 'viral_titles.txt';
    a.click();
    URL.revokeObjectURL(url);
}

function scoreColor(s) {
    if (s >= 8) return '#10b981';
    if (s >= 6) return '#f59e0b';
    return '#ef4444';
}

// ── TAB 3: Thumbnail Preview ───────────────────────────────────
// File upload
const uploadArea  = document.getElementById('upload-area');
const thumbFile   = document.getElementById('thumb-file');
let currentImgSrc = null;

uploadArea.addEventListener('click', () => thumbFile.click());
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.style.borderColor = 'var(--accent)'; });
uploadArea.addEventListener('dragleave', () => uploadArea.style.borderColor = '');
uploadArea.addEventListener('drop', e => {
    e.preventDefault();
    uploadArea.style.borderColor = '';
    const file = e.dataTransfer.files[0];
    if (file) loadThumb(file);
});
thumbFile.addEventListener('change', e => { if (e.target.files[0]) loadThumb(e.target.files[0]); });

function loadThumb(file) {
    const reader = new FileReader();
    reader.onload = ev => {
        currentImgSrc = ev.target.result;
        updateUploadLabel(file.name);
        updatePreviews();
    };
    reader.readAsDataURL(file);
}

function updateUploadLabel(name) {
    uploadArea.querySelector('.upload-label').textContent = '✅ ' + name;
}

// Live text inputs
['preview-title','preview-channel','preview-views','preview-duration'].forEach(id => {
    document.getElementById(id).addEventListener('input', updatePreviews);
});

function updatePreviews() {
    const title    = document.getElementById('preview-title').value;
    const channel  = document.getElementById('preview-channel').value;
    const views    = document.getElementById('preview-views').value;
    const duration = document.getElementById('preview-duration').value;
    const src      = currentImgSrc;

    // Avatar initials
    const initials = channel.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

    // ── HOME ──
    setThumb('home-thumb', 'home-placeholder', src);
    setText('home-title', title);
    setText('home-channel', channel);
    setText('home-views', views + ' · 2 months ago');
    setText('home-duration', duration);
    setText('home-avatar', initials);

    // ── SUGGESTED ──
    setThumb('sug-thumb', 'sug-placeholder', src);
    setText('sug-title', title);
    setText('sug-channel', channel);
    setText('sug-views', views);
    setText('sug-duration', duration);

    // ── MOBILE ──
    setThumb('mob-thumb', 'mob-placeholder', src);
    setText('mob-title', title);
    setText('mob-channel', channel + ' · ' + views + ' · 2 months ago');
    setText('mob-duration', duration);
    setText('mob-avatar', initials);
}

function setThumb(imgId, phId, src) {
    const img = document.getElementById(imgId);
    const ph  = document.getElementById(phId);
    if (src) {
        img.src = src;
        img.classList.remove('hidden');
        ph.classList.add('hidden');
    } else {
        img.classList.add('hidden');
        ph.classList.remove('hidden');
    }
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

// Mode tabs
document.querySelectorAll('.mode-tab').forEach(btn => {
    btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        document.querySelectorAll('.mode-tab').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.preview-stage').forEach(s => s.classList.add('hidden'));
        btn.classList.add('active');
        document.getElementById(`preview-${mode}`).classList.remove('hidden');
    });
});

// ── Utility ────────────────────────────────────────────────────
function setLoading(btn, spinner, loading, defaultText = '') {
    btn.disabled = loading;
    const span = btn.querySelector('.btn-text');
    if (loading) {
        if (span) span.textContent = 'Loading...';
        spinner.classList.remove('hidden');
    } else {
        if (span && defaultText) span.textContent = defaultText;
        spinner.classList.add('hidden');
    }
}

function setLoadingText(btn, text) {
    const span = btn.querySelector('.btn-text');
    if (span) span.textContent = text;
}

// Init live preview
updatePreviews();
