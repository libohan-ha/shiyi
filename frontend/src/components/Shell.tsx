import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, BookOpen, ChevronRight, Command, Home, Leaf, LogOut, PanelLeftClose, Plus, Search, Settings, Sparkles, SquarePen } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { api, post, queryClient } from '../api'
import { subjectName, subjects } from '../lib'
import type { ItemPage, Stats, User } from '../types'
import { EditorProvider, useEditor } from './Editor'
import { Empty, Logo, Modal, Spinner } from './ui'

const navigation = [{ to: '/', label: '今日复习', en: 'Today', icon: Home }, { to: '/library', label: '知识库', en: 'Library', icon: BookOpen }, { to: '/mistakes', label: '错题本', en: 'Mistakes', icon: SquarePen }, { to: '/statistics', label: '学习足迹', en: 'Insights', icon: BarChart3 }]
export function Shell({ user }: { user: User }) { return <EditorProvider userId={user.id}><Workspace user={user}/></EditorProvider> }

function Workspace({ user }: { user: User }) {
  const edit = useEditor()
  const [search, setSearch] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const stats = useQuery({ queryKey: ['stats'], queryFn: () => api<Stats>('/stats') })
  const current = navigation.find(n => location.pathname === n.to)
  useEffect(() => { setMobileOpen(false) }, [location.pathname])
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.closest('input, textarea, select, [contenteditable], dialog')) return
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearch(true) }
      if (e.key.toLowerCase() === 'n' && !e.metaKey && !e.ctrlKey) { e.preventDefault(); edit() }
    }
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  }, [edit])
  const logout = async () => { try { await post('/auth/logout'); queryClient.clear(); navigate('/login', { replace: true }) } catch (e) { toast.error((e as Error).message) } }
  return <div className={`app-shell ${location.pathname === '/review' ? 'review-shell' : ''}`}>
    <a className="skip-link" href="#main">跳到内容</a>
    {mobileOpen && <button className="sidebar-overlay" aria-label="收起导航" onClick={() => setMobileOpen(false)}/>}
    <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}><Link to="/" className="brand-link" aria-label="拾忆首页"><Logo/></Link><div className="workspace-label"><span className="status-dot"/>我的学习空间<span>PERSONAL</span></div>
      <nav className="main-nav" aria-label="主导航">{navigation.map(n => <NavLink key={n.to} to={n.to} end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><n.icon size={19} strokeWidth={1.7}/><span>{n.label}</span>{n.to === '/' && !!stats.data?.today.due && <b>{stats.data.today.due}</b>}</NavLink>)}</nav>
      <div className="sidebar-section"><div className="nav-section-label">我的科目 <span>03</span></div>{subjects.map(s => <Link className="subject-nav" key={s.id} to={`/library?subject=${s.id}`}><span className={`subject-dot ${s.color}`}/><span>{s.name}</span><small>{stats.data?.subjects.find(x => x.subject === s.id)?.total ?? 0}</small></Link>)}</div>
      <div className="sidebar-bottom"><div className="sidebar-note"><Leaf size={24} strokeWidth={1.3}/><p>每一次想起，<br/>都在让记忆扎根。</p><span>A LITTLE, EVERY DAY.</span></div><NavLink className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to="/settings"><Settings size={19} strokeWidth={1.7}/><span>偏好与连接</span></NavLink><div className="user-panel"><div className="avatar">{user.display_name.slice(0, 1)}</div><div><strong>{user.display_name}</strong><span>长期主义练习生</span></div><button onClick={() => void logout()} className="icon-button" aria-label="退出登录" title="退出登录"><LogOut size={17}/></button></div></div>
    </aside>
    <div className="workspace"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" onClick={() => setMobileOpen(!mobileOpen)} aria-label="展开导航"><PanelLeftClose size={21}/></button><span className="breadcrumb-root">学习工作台</span><ChevronRight size={13}/><strong>{current?.label ?? (location.pathname === '/settings' ? '偏好与连接' : location.pathname === '/review' ? '专注复习' : '知识详情')}</strong></div><div className="topbar-actions"><button className="global-search" onClick={() => setSearch(true)} aria-label="搜索知识"><Search size={16}/><span>搜索你的知识</span><kbd>⌘ K</kbd></button><span className="header-divider"/><button className="button primary small" onClick={() => edit()}><Plus size={17}/><span>记录新知</span></button></div></header>
      <main id="main" className={`main-content ${location.pathname === '/review' ? 'review-main' : ''}`}><Outlet context={{ user }}/></main>
      <footer className="workspace-footer"><span><Leaf size={13}/>拾忆 · 让知识慢慢生根</span><span>由 FSRS 科学安排每次重逢</span></footer>
    </div>
    <nav className="mobile-bottom" aria-label="手机导航">{navigation.map(n => <NavLink key={n.to} to={n.to} end><n.icon size={20}/><span>{n.label}</span></NavLink>)}<NavLink to="/settings"><Settings size={20}/><span>设置</span></NavLink></nav>
    {search && <SearchDialog onClose={() => setSearch(false)}/>}
  </div>
}

function SearchDialog({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  useEffect(() => { const timer = setTimeout(() => setQuery(input), 250); return () => clearTimeout(timer) }, [input])
  const result = useQuery({ queryKey: ['items', 'search', query], queryFn: () => api<ItemPage>(`/items?q=${encodeURIComponent(query)}&page_size=8`), enabled: query.trim().length > 0 })
  return <Modal title="找到那条记忆" onClose={onClose} className="search-modal"><div className="search-dialog-input"><Search size={21}/><input autoFocus value={input} onChange={e => setInput(e.target.value)} placeholder="搜索标题、正文、解析或标签…" aria-label="全局搜索"/>{result.isFetching && <Spinner/>}</div><div className="search-results">{!query ? <Empty title="知识，总有迹可循" description="输入一个关键词，找回你记录过的内容。" icon={<Command size={28}/>}/> : result.data?.items.length ? result.data.items.map(item => <button key={item.id} onClick={() => { navigate(`/items/${item.id}`); onClose() }}><BookOpen size={19}/><span><strong>{item.title}</strong><small>{subjectName(item.subject)} · {item.tags.join(' / ') || '未添加标签'}</small></span><ChevronRight size={17}/></button>) : !result.isFetching && <Empty title="暂时没有找到" description="换一个关键词，或检查一下拼写。"/>}</div><div className="search-footer"><Sparkles size={14}/>也可以搜索你在错题里写下的反思</div></Modal>
}
