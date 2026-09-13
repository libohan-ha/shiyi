import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { ApiError, api } from './api'
import type { User } from './types'
import { Shell } from './components/Shell'
import { Empty, ErrorState, Loading } from './components/ui'
import Auth from './pages/Auth'
import Dashboard from './pages/Dashboard'
import Library from './pages/Library'
import ItemDetail from './pages/ItemDetail'
import Review from './pages/Review'
import Statistics from './pages/Statistics'
import Settings from './pages/Settings'

function Protected() {
  const user = useQuery({ queryKey: ['me'], queryFn: () => api<User>('/auth/me'), retry: false })
  if (user.isPending) return <Loading/>
  if (user.error instanceof ApiError && user.error.status === 401) return <Navigate to="/login" replace/>
  if (user.error) return <ErrorState error={user.error} retry={() => void user.refetch()}/>
  return <Shell user={user.data!}/>
}

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('页面出现异常', error, info.componentStack) }
  render() { return this.state.failed ? <div className="fatal-error"><Empty title="页面暂时走神了" description="已保存的知识仍然在。重新加载后继续。" action={<button className="button primary" onClick={() => window.location.reload()}>重新加载</button>}/></div> : this.props.children }
}

export default function App() {
  return <ErrorBoundary><Routes><Route path="/login" element={<Auth/>}/><Route element={<Protected/>}><Route index element={<Dashboard/>}/><Route path="library" element={<Library/>}/><Route path="mistakes" element={<Library mistakes/>}/><Route path="items/:id" element={<ItemDetail/>}/><Route path="review" element={<Review/>}/><Route path="statistics" element={<Statistics/>}/><Route path="settings" element={<Settings/>}/><Route path="*" element={<Empty title="这条小路，还没有通往这里" description="回到熟悉的学习空间，继续你的积累。" action={<Link className="button primary" to="/">回到首页</Link>}/>}/></Route></Routes></ErrorBoundary>
}
