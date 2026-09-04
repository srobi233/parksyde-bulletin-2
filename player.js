/* The Bright Side — player.
 *
 * Reads output/latest.json and plays the day's bulletin.
 *
 * WHY THIS IS A PLAYLIST AND NOT ONE FILE. The original player fetched
 * output/latest.mp3. That file has never existed. generate_bulletin.py writes
 * ONE MP3 PER SPOKEN LINE — output/<date>/audio/seg1_open_line0.mp3 and so on,
 * because that is how ElevenLabs is called, once per line with the right
 * voice. So the player asked for a file that was never written, fell back to
 * its built-in SAMPLE, and showed six invented stories about the Bremer River
 * and the Broncos to anyone who opened it. It looked like it was working.
 * That is worse than looking broken, and it is why the fallback below now
 * says plainly that it is not today's bulletin.
 *
 * Joining the lines into one MP3 server-side would need ffmpeg in the daily
 * job. Playing them in order needs nothing at all, so this plays them in
 * order: one <audio> element, advanced on 'ended'. The progress bar counts
 * whole lines plus the fraction of the current one, which is honest without
 * needing any duration known in advance.
 */
(function () {
  'use strict';

  var REPO_BASE = 'https://raw.githubusercontent.com/srobi233/parksyde-bulletin-2/main/output';
  var MANIFEST_URL = REPO_BASE + '/latest.json';

  var $ = function (id) { return document.getElementById(id); };

  function fmtTime(s) {
    if (!isFinite(s) || s < 0) return '0:00';
    return Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');
  }

  function esc(str) {
    var d = document.createElement('div');
    d.textContent = str == null ? '' : String(str);
    return d.innerHTML;
  }

  var segments = [];   // [{id, title, script, lines:[{text, audio}]}]
  var playlist = [];   // [{segId, url, text}] — flattened, in broadcast order
  var track = 0;

  var audio = $('bs-audio');
  var playBtn = $('bs-play');
  var progress = $('bs-progress');
  var fill = $('bs-progress-fill');
  var timeEl = $('bs-time');
  var durationEl = $('bs-duration');
  var nowEl = $('bs-now-playing');

  var playIcon = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
  var pauseIcon = '<svg viewBox="0 0 24 24"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>';

  /* ---------------------------------------------------------------- */
  /* Rendering                                                        */
  /* ---------------------------------------------------------------- */

  function renderSegments(segs, playable) {
    var list = $('bs-segment-list');
    list.innerHTML = '';
    segs.forEach(function (seg, i) {
      var div = document.createElement('div');
      div.className = 'bs-segment';
      div.dataset.segId = seg.id || ('seg' + i);
      var lines = (seg.lines || []).length;
      var meta = playable && lines
        ? '<span class="bs-meta-icon"></span>' + lines + (lines === 1 ? ' line' : ' lines')
        : 'Segment ' + (i + 1);
      div.innerHTML =
        '<div class="bs-segment-num">' + String(i + 1).padStart(2, '0') + '</div>' +
        '<div class="bs-segment-content">' +
          '<h3>' + esc(seg.title) + '</h3>' +
          '<p>' + esc(seg.script) + '</p>' +
        '</div>' +
        '<div class="bs-segment-meta">' + meta + '</div>';

      div.addEventListener('click', function () {
        /* With audio, a click is "start this segment". Without it, a click is
           the only thing left that can be useful: open the full script. */
        var at = playlist.findIndex(function (t) { return t.segId === div.dataset.segId; });
        if (playable && at >= 0) {
          playTrack(at);
        } else {
          document.querySelectorAll('.bs-segment').forEach(function (s) {
            s.classList.remove('expanded');
          });
          div.classList.add('expanded');
        }
      });
      list.appendChild(div);
    });
  }

  function setActiveSegment(segId) {
    document.querySelectorAll('.bs-segment').forEach(function (el) {
      el.classList.toggle('playing', el.dataset.segId === segId);
    });
    var seg = segId && segments.find(function (s) { return s.id === segId; });
    nowEl.textContent = seg ? '◉ ' + seg.title : "◉ Today's Bulletin";
  }

  /* ---------------------------------------------------------------- */
  /* Playback                                                         */
  /* ---------------------------------------------------------------- */

  function playTrack(i) {
    if (i < 0 || i >= playlist.length) return;
    track = i;
    audio.src = playlist[i].url;
    setActiveSegment(playlist[i].segId);
    audio.play().catch(function (err) {
      /* Autoplay refusal is normal on a first load and is not an error worth
         shouting about; a genuinely missing file is. Either way the run does
         not continue silently. */
      console.warn('Bright Side: could not play ' + playlist[i].url + ' — ' + err.message);
    });
  }

  function paint() {
    var within = (isFinite(audio.duration) && audio.duration > 0)
      ? audio.currentTime / audio.duration : 0;
    var pct = playlist.length ? ((track + within) / playlist.length) * 100 : 0;
    fill.style.width = pct + '%';
    timeEl.textContent = 'line ' + (track + 1) + ' / ' + playlist.length;
  }

  playBtn.addEventListener('click', function () {
    if (!playlist.length) return;
    if (audio.paused) {
      if (!audio.src) playTrack(0); else audio.play().catch(function () {});
    } else {
      audio.pause();
    }
  });

  audio.addEventListener('play', function () {
    playBtn.classList.add('playing'); playBtn.innerHTML = pauseIcon;
  });
  audio.addEventListener('pause', function () {
    playBtn.classList.remove('playing'); playBtn.innerHTML = playIcon;
  });
  audio.addEventListener('timeupdate', paint);
  audio.addEventListener('ended', function () {
    if (track + 1 < playlist.length) playTrack(track + 1);
    else { setActiveSegment(null); fill.style.width = '100%'; }
  });
  audio.addEventListener('error', function () {
    /* One missing line must not end the bulletin. Skip it, say so, carry on —
       the same rule the generator uses for a failed voice. */
    console.warn('Bright Side: skipping missing audio ' + (playlist[track] || {}).url);
    if (track + 1 < playlist.length) playTrack(track + 1);
  });

  progress.addEventListener('click', function (e) {
    if (!playlist.length) return;
    var rect = progress.getBoundingClientRect();
    var pct = (e.clientX - rect.left) / rect.width;
    playTrack(Math.min(playlist.length - 1, Math.floor(pct * playlist.length)));
  });

  /* ---------------------------------------------------------------- */
  /* Load                                                             */
  /* ---------------------------------------------------------------- */

  function unavailable(why) {
    /* Never dress an outage as a bulletin. The old player showed six made-up
       stories when the fetch failed; anyone reading them had no way to know
       they were not today's news. */
    console.warn('Bright Side: ' + why);
    segments = [];
    playlist = [];
    $('bs-date').textContent = '—';
    playBtn.disabled = true;
    timeEl.textContent = '';
    durationEl.textContent = '--:--';
    $('bs-segment-list').innerHTML =
      '<div class="bs-loading">Today’s bulletin isn’t available yet. ' +
      'It is written fresh each morning at 6am AEST — try again shortly.</div>';
  }

  function load() {
    fetch(MANIFEST_URL, { cache: 'no-cache' })
      .then(function (res) {
        if (!res.ok) throw new Error('manifest fetch failed: ' + res.status);
        return res.json();
      })
      .then(function (data) {
        segments = data.segments || [];
        if (!segments.length) throw new Error('no segments in manifest');

        $('bs-date').textContent = data.day || data.date || '';

        playlist = [];
        segments.forEach(function (seg) {
          (seg.lines || []).forEach(function (line) {
            if (line.audio) {
              playlist.push({ segId: seg.id, url: REPO_BASE + '/' + line.audio, text: line.text });
            }
          });
        });

        var playable = playlist.length > 0;
        renderSegments(segments, playable);
        playBtn.disabled = !playable;

        if (playable) {
          durationEl.textContent = playlist.length + ' lines';
          timeEl.textContent = 'line 1 / ' + playlist.length;
        } else {
          /* Scripts without voices is a real, useful state — it is what
             happens when the ElevenLabs key is absent — so say which it is
             rather than greying out with no explanation. */
          durationEl.textContent = 'read only';
          timeEl.textContent = 'no audio today';
        }
      })
      .catch(function (e) { unavailable(e.message); });
  }

  load();
})();
