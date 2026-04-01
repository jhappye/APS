/**
 * APS AI 助手 · 客户端 SDK V2
 * ================================
 * 基于真实接口重写，完整流程：
 *   登录 → 触发评估 → 轮询状态 → 流式获取 AI 报告 → 多轮追问
 *   业务问答（流式，多轮对话）
 */

const ApsAI = (() => {

  // ─── 配置（支持运行时覆盖）─────────────────────────
  // 使用方式：在引入 SDK 前定义 window.APS_CONFIG = { BASE_URL: '...' }
  // 例如：<script>window.APS_CONFIG = { BASE_URL: 'http://your-gateway:8001' };</script>
  //       <script src="aps-ai-sdk.js"></script>
  const CONFIG = {
    BASE_URL: (window.APS_CONFIG && window.APS_CONFIG.BASE_URL) || 'http://localhost:8001',
  }

  // 报表页面地址也从配置读取（默认同网关地址）
  function getReportUrl() {
    const base = (window.APS_CONFIG && window.APS_CONFIG.BASE_URL) || CONFIG.BASE_URL
    // 从 BASE_URL 中提取 host:port（如 http://192.168.1.1:8001 → 192.168.1.1:8000）
    const match = base.match(/^https?:\/\/([^\/:]+)(?::(\d+))?/)
    if (match) {
      const host = match[1]
      const port = match[2] ? String(parseInt(match[2]) - 1) : '8000'  // 8001→8000
      return `http://${host}:${port}/report?t=${Date.now()}`
    }
    return `http://localhost:8000/report?t=${Date.now()}`
  }

  // ─── 内部状态 ─────────────────────────────────────
  let _token = ''
  let _userId = ''
  let _userName = ''
  let _conversationId = ''

  // ─── 基础请求 ──────────────────────────────────────
  function _headers(extra = {}) {
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${_token}`,
      ...extra,
    }
  }

  async function _post(path, body = {}) {
    const r = await fetch(`${CONFIG.BASE_URL}${path}`, {
      method: 'POST', headers: _headers(), body: JSON.stringify(body),
    })
    return r.json()
  }

  async function _get(path) {
    const r = await fetch(`${CONFIG.BASE_URL}${path}`, { headers: _headers() })
    return r.json()
  }

  // ════════════════════════════════════════════════
  //  登录
  // ════════════════════════════════════════════════

  /**
   * 登录
   * @param {string} userName
   * @param {string} password
   * @param {number} [orgId]
   * @returns {Promise<{token, userId, userName, fullName}>}
   */
  async function login(userName, password, orgId) {
    const data = await _post('/ai/login', { userName, password, orgId })
    if (data.code !== 0) throw new Error(data.message || '登录失败')
    _token    = data.data.token
    _userId   = data.data.userId
    _userName = data.data.userName
    console.log('[ApsAI] 登录成功，userId =', _userId)
    return data.data
  }

  /** 是否已登录 */
  function isLoggedIn() { return !!_token }

  // ════════════════════════════════════════════════
  //  插单评估
  // ════════════════════════════════════════════════

  /**
   * 完整插单评估流程（推荐使用此方法）
   *
   * @param {object} callbacks
   *   onStatus(msg)          状态变化时（如"正在分析..."）
   *   onChunk(text)          流式文字块（打字机效果）
   *   onDone(answer, convId) 完成时
   *   onError(err)           出错时
   */
  async function evaluateRushOrders(callbacks = {}) {
    const { onStatus, onChunk, onDone, onError } = callbacks

    try {
      // Step 1: 触发评估
      onStatus && onStatus('正在提交评估请求...')
      const startData = await _post('/ai/rush-order/evaluate/start')
      if (startData.code !== 0) throw new Error(startData.message)
      const taskId = startData.data.taskId

      // Step 2: 轮询状态（每3秒，最多5分钟）
      onStatus && onStatus('APS 正在运算，请稍候...')
      await _pollEvalStatus(taskId, onStatus)

      // Step 3: 流式获取 AI 分析报告
      onStatus && onStatus('正在生成 AI 分析报告...')
      await _streamAnalyze(taskId, { onChunk, onDone, onError })

    } catch (e) {
      onError && onError({ code: 'ERROR', message: e.message })
    }
  }

  async function _pollEvalStatus(taskId, onStatus) {
    const maxRetry = 100
    for (let i = 0; i < maxRetry; i++) {
      await _sleep(3000)
      const data = await _get(`/ai/rush-order/evaluate/status/${taskId}`)
      if (data.code !== 0) throw new Error(data.message)
      const { status, message } = data.data
      if (status === 'completed') return
      if (status === 'failed') throw new Error(message || '评估失败')
      onStatus && onStatus(message || 'APS 运算中...')
    }
    throw new Error('评估超时，请稍后重试')
  }

  async function _streamAnalyze(taskId, { onChunk, onDone, onError }) {
    const resp = await fetch(
      `${CONFIG.BASE_URL}/ai/rush-order/evaluate/analyze/${taskId}/stream`,
      { method: 'POST', headers: _headers() }
    )

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      onError && onError({ code: 'HTTP_ERROR', message: `请求失败 ${resp.status}` })
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = '', fullAnswer = '', convId = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        let event
        try { event = JSON.parse(line.slice(6)) } catch { continue }
        switch (event.type) {
          case 'chunk':
            fullAnswer += event.content
            onChunk && onChunk(event.content)
            break
          case 'done':
            convId = event.conversationId || ''
            _conversationId = convId
            onDone && onDone(fullAnswer, convId)
            break
          case 'error':
            onError && onError({ code: 'AI_ERROR', message: event.message })
            break
        }
      }
    }
  }

  // ════════════════════════════════════════════════
  //  业务问答
  // ════════════════════════════════════════════════

  /**
   * 流式业务问答（支持多轮对话）
   * @param {string} message
   * @param {object} callbacks  { onChunk, onDone, onError }
   */
  async function chat(message, callbacks = {}) {
    const { onChunk, onDone, onError } = callbacks
    console.log('[ApsAI] chat 请求发送:', { message, userId: _userId, conversationId: _conversationId, baseUrl: CONFIG.BASE_URL })

    let resp
    try {
      resp = await fetch(`${CONFIG.BASE_URL}/ai/chat/stream`, {
        method: 'POST',
        headers: _headers(),
        body: JSON.stringify({ message, userId: _userId, conversationId: _conversationId }),
      })
    } catch (e) {
      console.error('[ApsAI] fetch 异常:', e)
      onError && onError({ code: 'NETWORK_ERROR', message: `网络错误: ${e.message}` })
      return
    }

    console.log('[ApsAI] 收到响应:', resp.status, resp.statusText)
    if (!resp.ok) {
      const text = await resp.text().catch(() => '')
      console.error('[ApsAI] HTTP 错误:', resp.status, text)
      onError && onError({ code: 'HTTP_ERROR', message: `请求失败 ${resp.status}: ${text.slice(0, 100)}` })
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = '', fullAnswer = ''
    console.log('[ApsAI] 开始读取流...')

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        console.log('[ApsAI] 流读取完成, fullAnswer长度=', fullAnswer.length)
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        let event
        try { event = JSON.parse(line.slice(6)) } catch (e) {
          console.warn('[ApsAI] JSON 解析失败:', line.slice(0, 50))
          continue
        }
        switch (event.type) {
          case 'chunk':
            fullAnswer += event.content
            onChunk && onChunk(event.content)
            break
          case 'done':
            _conversationId = event.conversationId || _conversationId
            console.log('[ApsAI] done 事件, conversationId=', event.conversationId)
            onDone && onDone(fullAnswer, event.conversationId)
            break
          case 'error':
            console.error('[ApsAI] error 事件:', event.message)
            onError && onError({ code: 'AI_ERROR', message: event.message })
            break
        }
      }
    }
  }

  /** 清除对话历史，开启新对话 */
  async function clearConversation() {
    if (_conversationId) {
      await fetch(`${CONFIG.BASE_URL}/ai/conversation/${_conversationId}?userId=${_userId}`, {
        method: 'DELETE', headers: _headers(),
      }).catch(() => {})
    }
    _conversationId = ''
  }

  function _sleep(ms) { return new Promise(r => setTimeout(r, ms)) }
  function getToken() { return _token }
  function getConversationId() { return _conversationId }

  return { login, isLoggedIn, evaluateRushOrders, chat, clearConversation, getToken, getConversationId, getReportUrl }
})()


/* ══════════════════════════════════════════════════════
   聊天窗口 UI 组件
   用法：ApsAIChatWidget.mount('#container', { mode: 'chat' | 'evaluate' })
   ══════════════════════════════════════════════════════ */

const ApsAIChatWidget = (() => {

  const STYLES = `
    .aps-wrap{display:flex;flex-direction:column;height:100%;font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:#f7f8fa;border-radius:12px;overflow:hidden}
    .aps-header{padding:14px 18px;background:#1a56db;color:#fff;font-size:15px;font-weight:500;display:flex;align-items:center;gap:8px}
    .aps-header .dot{width:8px;height:8px;background:#4ade80;border-radius:50%}
    .aps-msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
    .aps-msg{display:flex;gap:8px;align-items:flex-start}
    .aps-msg.user{flex-direction:row-reverse}
    .aps-avatar{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0}
    .aps-msg.bot .aps-avatar{background:#dbeafe}
    .aps-msg.user .aps-avatar{background:#1a56db;color:#fff}
    .aps-bubble{max-width:76%;padding:9px 13px;border-radius:10px;font-size:13px;line-height:1.75;word-break:break-word}
    .aps-msg.bot .aps-bubble{background:#fff;color:#1f2937;border:1px solid #e5e7eb;border-top-left-radius:3px}
    .aps-msg.user .aps-bubble{background:#1a56db;color:#fff;border-top-right-radius:3px}
    .aps-status{font-size:12px;color:#6b7280;padding:4px 14px;font-style:italic}
    .aps-cursor{display:inline-block;width:2px;height:13px;background:#1a56db;margin-left:2px;animation:blink .8s infinite;vertical-align:text-bottom}
    @keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
    .aps-suggested{padding:0 14px 10px;display:flex;flex-wrap:wrap;gap:5px}
    .aps-sq{padding:4px 11px;background:#fff;border:1px solid #d1d5db;border-radius:16px;font-size:12px;color:#374151;cursor:pointer;transition:all .15s}
    .aps-sq:hover{background:#eff6ff;border-color:#1a56db;color:#1a56db}
    .aps-input-bar{padding:10px 14px;background:#fff;border-top:1px solid #e5e7eb;display:flex;gap:8px;align-items:flex-end}
    .aps-input-bar textarea{flex:1;border:1px solid #d1d5db;border-radius:8px;padding:7px 11px;font-size:13px;resize:none;outline:none;min-height:34px;max-height:100px;line-height:1.5;font-family:inherit}
    .aps-input-bar textarea:focus{border-color:#1a56db}
    .aps-send{width:34px;height:34px;background:#1a56db;color:#fff;border:none;border-radius:8px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s;flex-shrink:0}
    .aps-send:hover{background:#1e40af}
    .aps-send:disabled{background:#9ca3af;cursor:not-allowed}
    .aps-new{font-size:11px;color:#9ca3af;cursor:pointer;text-align:center;padding:3px 0 7px;text-decoration:underline}
    .aps-new:hover{color:#1a56db}
    .aps-login-box{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:12px;padding:24px}
    .aps-login-box h3{font-size:16px;color:#1f2937;font-weight:500}
    .aps-login-box input{width:100%;padding:9px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;outline:none}
    .aps-login-box input:focus{border-color:#1a56db}
    .aps-login-btn{width:100%;padding:9px;background:#1a56db;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer}
    .aps-login-btn:hover{background:#1e40af}
    .aps-err{color:#ef4444;font-size:12px}
    .aps-eval-btn{margin:8px 14px;padding:8px 0;background:#1a56db;color:#fff;border:none;border-radius:8px;font-size:13px;cursor:pointer;width:calc(100% - 28px)}
    .aps-eval-btn:hover{background:#1e40af}
    .aps-eval-btn:disabled{background:#9ca3af;cursor:not-allowed}
  `

  const SUGGESTED = [
    '最近有哪些物料缺料预警？',
    '本周产能负荷情况如何？',
    '近两周有哪些交期风险？',
    '查询订单 SO20250001 进度',
  ]

  function mount(selector, options = {}) {
    const container = typeof selector === 'string' ? document.querySelector(selector) : selector
    if (!container) return console.error('[ApsAIChatWidget] 找不到容器', selector)

    if (!document.getElementById('aps-styles')) {
      const s = document.createElement('style')
      s.id = 'aps-styles'; s.textContent = STYLES
      document.head.appendChild(s)
    }

    // 若未登录，先显示登录界面
    if (!ApsAI.isLoggedIn()) {
      _renderLogin(container, () => _renderChat(container, options))
    } else {
      _renderChat(container, options)
    }
  }

  function _renderLogin(container, onSuccess) {
    container.innerHTML = `
      <div class="aps-wrap">
        <div class="aps-header"><span class="dot"></span>APS AI 助手 · 登录</div>
        <div class="aps-login-box">
          <h3>请登录后使用</h3>
          <input id="aps-un" placeholder="用户名" />
          <input id="aps-pw" type="password" placeholder="密码" />
          <button class="aps-login-btn" id="aps-login-btn">登 录</button>
          <span class="aps-err" id="aps-err"></span>
        </div>
      </div>`

    container.querySelector('#aps-login-btn').addEventListener('click', async () => {
      const un = container.querySelector('#aps-un').value.trim()
      const pw = container.querySelector('#aps-pw').value.trim()
      const errEl = container.querySelector('#aps-err')
      const btn = container.querySelector('#aps-login-btn')
      if (!un || !pw) { errEl.textContent = '请填写用户名和密码'; return }
      btn.disabled = true; btn.textContent = '登录中...'
      try {
        await ApsAI.login(un, pw)
        onSuccess()
      } catch (e) {
        errEl.textContent = e.message || '登录失败'
        btn.disabled = false; btn.textContent = '登 录'
      }
    })
  }

  function _renderChat(container, options = {}) {
    const mode = options.mode || 'chat'  // 'chat' | 'evaluate'

    container.innerHTML = `
      <div class="aps-wrap">
        <div class="aps-header"><span class="dot"></span>APS AI 助手</div>
        <div class="aps-msgs" id="aps-msgs">
          <div class="aps-msg bot">
            <div class="aps-avatar">🤖</div>
            <div class="aps-bubble">您好！我是 APS 业务助手。<br>
              ${mode === 'evaluate'
                ? '点击下方按钮可触发<strong>插单评估</strong>，完成后我会为您生成分析报告。'
                : '您可以问我：<strong>订单进度、缺料预警、产能负荷、交期风险</strong>等。'}
            </div>
          </div>
        </div>
        ${mode === 'evaluate' ? `<button class="aps-eval-btn" id="aps-eval-btn">▶ 触发插单评估</button>` : ''}
        ${mode === 'chat' ? `<div class="aps-suggested" id="aps-sq">${SUGGESTED.map(q=>`<button class="aps-sq">${q}</button>`).join('')}</div>` : ''}
        <div class="aps-input-bar">
          <textarea id="aps-in" placeholder="输入问题或追问..." rows="1"></textarea>
          <button class="aps-send" id="aps-send">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          </button>
        </div>
        <div class="aps-new" id="aps-new">开启新对话</div>
      </div>`

    const msgsEl = container.querySelector('#aps-msgs')
    const inputEl = container.querySelector('#aps-in')
    const sendBtn = container.querySelector('#aps-send')
    const sqEl = container.querySelector('#aps-sq')
    let loading = false

    function fmt(text) {
      return text
        .replace(/^### (.+)$/gm, '<p style="font-weight:500;font-size:13px;margin:8px 0 2px;color:#374151">$1</p>')
        .replace(/^## (.+)$/gm, '<p style="font-weight:600;font-size:14px;margin:10px 0 4px;color:#1f2937">$1</p>')
        .replace(/^# (.+)$/gm, '<p style="font-weight:600;font-size:15px;margin:10px 0 4px;color:#111827">$1</p>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/^- (.+)$/gm, '<span style="display:block;padding-left:12px">• $1</span>')
        .replace(/\n/g, '<br>')
    }
    function addMsg(role, text) {
      const div = document.createElement('div')
      div.className = `aps-msg ${role}`
      div.innerHTML = `<div class="aps-avatar">${role==='bot'?'🤖':'👤'}</div><div class="aps-bubble">${fmt(text)}</div>`
      msgsEl.appendChild(div); msgsEl.scrollTop = msgsEl.scrollHeight
      return div.querySelector('.aps-bubble')
    }

    function showStatus(msg) {
      let el = container.querySelector('.aps-status')
      if (!el) { el = document.createElement('div'); el.className = 'aps-status'; msgsEl.appendChild(el) }
      el.textContent = msg; msgsEl.scrollTop = msgsEl.scrollHeight
    }
    function clearStatus() {
      const el = container.querySelector('.aps-status'); if (el) el.remove()
    }

    async function sendMsg(text) {
      if (loading || !text.trim()) return
      // 评估模式下：用户回复"是"/"查看详细"，直接展示报表链接
      if (mode === 'evaluate' && (text.trim() === '是' || text.includes('查看详细'))) {
        addMsg('user', text)
        const reportUrl = ApsAI.getReportUrl()
        const botBubble = addMsg('bot', `📊 请点击查看详细数据：<a href="${reportUrl}" target="_blank" style="color:#1a56db;text-decoration:underline">${reportUrl}</a>`)
        return
      }
      loading = true; sendBtn.disabled = true
      if (sqEl) sqEl.style.display = 'none'
      addMsg('user', text)
      const bubble = addMsg('bot', '')
      const cursor = document.createElement('span'); cursor.className = 'aps-cursor'
      bubble.appendChild(cursor)
      let full = ''

      try {
        await ApsAI.chat(text, {
          onChunk: c => { full += c; bubble.innerHTML = fmt(full); bubble.appendChild(cursor); msgsEl.scrollTop = msgsEl.scrollHeight },
          onDone:  a => { bubble.innerHTML = fmt(a || full); msgsEl.scrollTop = msgsEl.scrollHeight },
          onError: e => { bubble.innerHTML = `<span style="color:#ef4444">❌ ${e.message}</span>` },
        })
      } catch (e) {
        console.error('[ApsAI] sendMsg 异常:', e)
        bubble.innerHTML = `<span style="color:#ef4444">❌ 调用异常: ${e.message}</span>`
      } finally {
        loading = false; sendBtn.disabled = false
      }
    }

    sendBtn.addEventListener('click', () => { const t=inputEl.value.trim(); inputEl.value=''; inputEl.style.height='auto'; sendMsg(t) })
    inputEl.addEventListener('keydown', e => { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();const t=inputEl.value.trim();inputEl.value='';inputEl.style.height='auto';sendMsg(t)} })
    inputEl.addEventListener('input', () => { inputEl.style.height='auto'; inputEl.style.height=Math.min(inputEl.scrollHeight,100)+'px' })
    if (sqEl) sqEl.addEventListener('click', e => { if(e.target.classList.contains('aps-sq'))sendMsg(e.target.textContent) })
    container.querySelector('#aps-new').addEventListener('click', async () => {
      await ApsAI.clearConversation()
      msgsEl.innerHTML = `<div class="aps-msg bot"><div class="aps-avatar">🤖</div><div class="aps-bubble">新对话已开启，请问有什么可以帮您？</div></div>`
      if (sqEl) sqEl.style.display = 'flex'
    })

    // 插单评估按钮
    const evalBtn = container.querySelector('#aps-eval-btn')
    if (evalBtn) {
      evalBtn.addEventListener('click', async () => {
        evalBtn.disabled = true; evalBtn.textContent = '评估中...'
        const bubble = addMsg('bot', '')
        const cursor = document.createElement('span'); cursor.className = 'aps-cursor'
        bubble.appendChild(cursor)
        let full = ''

        await ApsAI.evaluateRushOrders({
          onStatus: msg => { showStatus(msg) },
          onChunk:  c => { clearStatus(); full+=c; bubble.innerHTML=fmt(full); bubble.appendChild(cursor); msgsEl.scrollTop=msgsEl.scrollHeight },
          onDone:   a => {
            const answer = a || full
            bubble.innerHTML = fmt(answer)
            msgsEl.scrollTop = msgsEl.scrollHeight
            evalBtn.disabled = false
            evalBtn.textContent = '▶ 重新评估'
            // 监听追问：用户回复"是"或"查看详细"时直接展示报表链接
            window._lastEvalAnswer = answer
          },
          onError:  e => { clearStatus(); bubble.innerHTML=`<span style="color:#ef4444">❌ ${e.message}</span>`; evalBtn.disabled=false; evalBtn.textContent='▶ 触发插单评估' },
        })
      })
    }
  }

  return { mount }
})()
