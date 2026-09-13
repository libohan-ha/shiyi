import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Check, Eye, EyeOff, Leaf, ShieldCheck } from 'lucide-react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api, post, queryClient } from '../api'
import type { User } from '../types'
import { Logo, Spinner } from '../components/ui'

export default function Auth() {
  const status = useQuery({ queryKey: ['auth-status'], queryFn: () => api<{ initialized: boolean; registration_open: boolean }>('/auth/status') })
  const me = useQuery({ queryKey: ['me'], queryFn: () => api<User>('/auth/me'), retry: false })
  const [mode, setMode] = useState<'login' | 'register' | null>(null)
  const register = mode === 'register' || (mode === null && status.data && !status.data.initialized)
  const [form, setForm] = useState({ username: '', password: '', display_name: '' })
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  if (me.data) return <Navigate to="/" replace/>
  return <div className="auth-page"><section className="auth-story"><Logo/><div className="auth-story-content"><span className="eyebrow">COLLECT. RECALL. GROW.</span><h1>让学过的，<br/>慢慢成为<span>你的。</span></h1><p>拾起一条知识，在恰好的时候再次想起。<br/>把每一天的小小积累，变成走向目标的底气。</p><div className="auth-orbit"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="orbit orbit-three"/><div className="orbit-center"><Leaf size={58} strokeWidth={1}/><span>生根 · 生长</span></div><div className="floating-note note-one"><span className="note-symbol">∫</span><div><strong>从理解，到熟悉</strong><small>数学 · 每一步都有依据</small></div><Check size={17}/></div><div className="floating-note note-two"><span className="note-symbol">Aa</span><div><strong>又一次，想起来了</strong><small>英语 · 让记忆渐渐清晰</small></div><span className="note-spark">✦</span></div><span className="orbit-dot dot-one"/><span className="orbit-dot dot-two"/></div></div><div className="auth-story-footer"><span>408 / 数学 / 英语</span><span>给认真学习的你。</span></div></section>
    <section className="auth-form-side"><div className="auth-mobile-brand"><Logo/></div><div className="auth-form-wrap"><span className="eyebrow">YOUR QUIET PLACE TO GROW</span><h2>{register ? '拥有你的学习空间' : '欢迎回来。'}</h2><p>{register ? '从今天的一点积累开始。' : '知识在这里，等你再次遇见。'}</p>
      <form onSubmit={async e => { e.preventDefault(); setError(''); setBusy(true); try { const user = await post<User>(register ? '/auth/register' : '/auth/login', register ? { ...form, display_name: form.display_name || '同学' } : { username: form.username, password: form.password }); queryClient.setQueryData(['me'], user); navigate('/', { replace: true }) } catch (err) { setError((err as Error).message) } finally { setBusy(false) } }}>
        {register && <label className="field">怎么称呼你<input autoComplete="nickname" value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} placeholder="你的昵称" maxLength={40}/></label>}
        <label className="field">用户名<input required minLength={3} maxLength={80} pattern="[a-zA-Z0-9_.@\-]+" autoComplete="username" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} placeholder="字母、数字或下划线"/></label>
        <label className="field">密码<div className="password-input"><input required minLength={register ? 10 : 1} maxLength={128} type={visible ? 'text' : 'password'} autoComplete={register ? 'new-password' : 'current-password'} value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} placeholder={register ? '至少 10 位，给知识一个安心的家' : '输入你的密码'}/><button type="button" className="icon-button" aria-label={visible ? '隐藏密码' : '显示密码'} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div></label>
        {(error || status.error) && <div role="alert" className="form-error">{error || (status.error as Error).message}</div>}
        <button className="button primary auth-submit" disabled={busy || status.isPending || !!status.error}>{busy ? <Spinner/> : <>{register ? '开始我的积累' : '进入学习空间'}<ArrowRight size={18}/></>}</button>
      </form>
      {status.data?.registration_open && status.data.initialized && <button className="text-button auth-switch" onClick={() => { setMode(register ? 'login' : 'register'); setError('') }}>{register ? '已有账号？回到登录' : '创建一个独立的学习账号'}</button>}
      <div className="auth-privacy"><ShieldCheck size={17}/><span>{!status.data?.initialized ? '创建后将关闭公开注册，成为你的私人空间' : '你的知识与学习记录，仅属于你'}</span></div></div><div className="auth-footer">不用一口气走很远，今天往前一点就好。</div></section></div>
}
