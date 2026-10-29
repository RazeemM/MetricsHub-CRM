/* MetricsHub CRM website tracking. Served by /api/public/t/<key>.js with this site's settings below.
 *
 * Use from the website (works before the script has loaded too):
 *   window.mhcrm = window.mhcrm || []
 *   mhcrm.push(['identify', { email: 'jane@example.com', first_name: 'Jane', company: 'Example' }])
 *   mhcrm.push(['track', 'Downloaded datasheet', { product: 'Hardware Sentry' }])
 *   mhcrm.push(['consent', true])   // when the site waits for consent; false forgets the visitor
 * Once loaded, mhcrm.identify(...), mhcrm.track(...), mhcrm.consent(...) and mhcrm.page() also work.
 */
;(function (w, d) {
  'use strict'
  var C = __CONFIG__
  if (w.__mhcrmLoaded) return
  w.__mhcrmLoaded = true

  var VID = '_mhcrm_v', SID = '_mhcrm_s', OK = '_mhcrm_c'
  var nav = w.navigator || {}
  var dnt = C.dnt && (nav.doNotTrack === '1' || w.doNotTrack === '1' || nav.msDoNotTrack === '1' || nav.globalPrivacyControl === true)
  var lastUrl = null

  function readCookie(name) {
    var m = d.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
    return m ? decodeURIComponent(m[1]) : null
  }
  function writeCookie(name, value, minutes) {
    var exp = minutes ? '; expires=' + new Date(Date.now() + minutes * 60000).toUTCString() : ''
    var secure = location.protocol === 'https:' ? '; Secure' : ''
    d.cookie = name + '=' + encodeURIComponent(value) + exp + '; path=/; SameSite=Lax' + secure
  }
  function dropCookie(name) {
    d.cookie = name + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
  }
  function uid() {
    if (w.crypto && w.crypto.randomUUID) return w.crypto.randomUUID()
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
    })
  }
  function allowed() {
    return !dnt && (!C.consent || readCookie(OK) === '1')
  }

  function send(events) {
    if (!allowed()) return
    var vid = readCookie(VID) || uid()
    var sid = readCookie(SID)
    var fresh = !sid
    sid = sid || uid()
    writeCookie(VID, vid, 60 * 24 * 395)
    writeCookie(SID, sid, C.session_minutes) // rolling: a session ends after this much inactivity
    var body = JSON.stringify({ vid: vid, sid: sid, new_session: fresh, events: events })
    try {
      if (nav.sendBeacon && nav.sendBeacon(C.endpoint, new Blob([body], { type: 'text/plain' }))) return
    } catch (e) {}
    try {
      w.fetch(C.endpoint, { method: 'POST', body: body, keepalive: true, mode: 'no-cors', headers: { 'Content-Type': 'text/plain' } })
    } catch (e) {}
  }

  function page() {
    var url = location.href.split('#')[0]
    if (url === lastUrl) return
    var ref = lastUrl || d.referrer
    lastUrl = url
    send([{ t: 'page', url: url, title: d.title, ref: ref }])
  }

  function identify(fields, form) {
    if (!fields || typeof fields !== 'object') return
    send([{ t: 'identify', url: location.href, fields: fields, form: form || null }])
  }

  function track(name, props) {
    if (!name) return
    send([{ t: 'event', url: location.href, name: String(name), props: props && typeof props === 'object' ? props : {} }])
  }

  function consent(given) {
    if (given) {
      var already = readCookie(OK) === '1'
      writeCookie(OK, '1', 60 * 24 * 395)
      if (!already && C.consent) {
        lastUrl = null
        page()
      }
    } else {
      writeCookie(OK, '0', 60 * 24 * 395)
      dropCookie(VID)
      dropCookie(SID)
    }
  }

  // Forms with an email field: send the fields the CRM knows when submitted. Never passwords, card numbers or
  // hidden fields; a form with data-mhcrm-ignore is skipped.
  var SKIP = /pass|card|cvc|cvv|iban|ssn|secret|token|captcha/i
  function onSubmit(ev) {
    var form = ev.target
    if (!form || form.tagName !== 'FORM' || form.hasAttribute('data-mhcrm-ignore')) return
    var fields = {}
    var hasEmail = false
    for (var i = 0; i < form.elements.length; i++) {
      var el = form.elements[i]
      var name = el.name || el.id
      if (!name || el.disabled || SKIP.test(name)) continue
      var type = (el.type || '').toLowerCase()
      if (type === 'password' || type === 'hidden' || type === 'file' || type === 'submit' || type === 'button') continue
      if ((type === 'checkbox' || type === 'radio') && !el.checked) continue
      var value = type === 'checkbox' ? 'true' : el.value
      if (!value) continue
      fields[name] = String(value).slice(0, 500)
      if (type === 'email' || /e[-_]?mail/i.test(name)) hasEmail = true
    }
    if (hasEmail) identify(fields, form.id || form.getAttribute('name') || location.pathname)
  }

  var api = {
    identify: identify,
    track: track,
    consent: consent,
    page: page,
    push: function (cmd) {
      if (!cmd || !cmd.length) return
      var fn = api[cmd[0]]
      if (typeof fn === 'function' && cmd[0] !== 'push') fn.apply(null, Array.prototype.slice.call(cmd, 1))
    },
  }
  var queued = w.mhcrm && w.mhcrm.length ? w.mhcrm : []
  w.mhcrm = api

  if (C.forms) d.addEventListener('submit', onSubmit, true)
  // single-page applications: count route changes as page views
  var push = w.history && w.history.pushState
  if (push) {
    w.history.pushState = function () {
      var r = push.apply(this, arguments)
      setTimeout(page, 0)
      return r
    }
    w.addEventListener('popstate', function () { setTimeout(page, 0) })
  }

  // consent() queued before load must apply before the first page view
  for (var i = 0; i < queued.length; i++) if (queued[i] && queued[i][0] === 'consent') api.push(queued[i])
  page()
  for (var j = 0; j < queued.length; j++) if (queued[j] && queued[j][0] !== 'consent') api.push(queued[j])
})(window, document)
