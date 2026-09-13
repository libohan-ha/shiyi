import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpen, Check, ChevronRight, Clock3, Flame, Leaf, Plus, Settings2, Sparkles, Sprout } from 'lucide-react'
import { Link, useOutletContext } from 'react-router-dom'
import { api } from '../api'
import { dateLabel, plainText, subjectName, subjects } from '../lib'
import type { Stats, User } from '../types'
import { useEditor } from '../components/Editor'
import { Empty, ErrorState, Heatmap, Loading, PageHeading, SectionTitle } from '../components/ui'

export default function Dashboard() {
  const { user } = useOutletContext<{ user: User }>()
  const edit = useEditor()
  const stats = useQuery({ queryKey: ['stats'], queryFn: () => api<Stats>('/stats'), refetchInterval: 30_000 })
  if (stats.isPending) return <Loading/>
  if (stats.error) return <ErrorState error={stats.error} retry={() => void stats.refetch()}/>
  const data = stats.data
  const today = data.today
  const ready = today.due + today.new_available
  const timeZone = user.preferences.timezone
  const localNow = new Date(data.server_time)
  const hour = Number(new Intl.DateTimeFormat('en-GB', { timeZone, hour: 'numeric', hourCycle: 'h23' }).format(localNow))
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '上午好' : hour < 18 ? '下午好' : '晚上好'
  const progress = Math.min(1, today.reviews / user.preferences.daily_goal)
  const date = new Intl.DateTimeFormat('zh-CN', { timeZone, month: 'long', day: 'numeric', weekday: 'long' }).format(localNow)
  const localDay = new Intl.DateTimeFormat('sv-SE', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(localNow)
  const examDays = user.preferences.exam_date ? Math.max(0, Math.round((Date.parse(user.preferences.exam_date) - Date.parse(localDay)) / 86400000)) : null
  const estimate = today.estimated_minutes >= 60 ? `${Math.floor(today.estimated_minutes / 60)} 小时${today.estimated_minutes % 60 ? ` ${today.estimated_minutes % 60} 分钟` : ''}` : `${today.estimated_minutes} 分钟`

  return <div className="dashboard page-enter">
    <PageHeading eyebrow="A LITTLE, EVERY DAY" title={`${greeting}，${user.display_name}。`} description="今天要记住的事，都在这里。" actions={<span className="date-chip"><span className="status-dot"/>{date}</span>}/>
    <section className="today-plan" aria-label="今日复习安排">
      <div className="today-plan-heading"><h2><Leaf size={18}/>今天的复习</h2>{ready > 0 && <span className="plan-estimate" title={today.estimate_from_history ? '根据最近 30 天各科的复习用时估算' : '记录不足时使用各科默认用时估算'}><Clock3 size={15}/>{today.estimate_from_history ? '本轮预计' : '本轮粗估'} {estimate}</span>}</div>
      <div className="plan-numbers">
        <div><strong>{today.due}</strong><span>待复习</span><small className={today.overdue ? 'plan-overdue' : ''}>{today.overdue ? `其中 ${today.overdue} 条已逾期` : '已学内容，按时巩固'}</small></div>
        <div><strong>{today.new_available}</strong><span>可新学</span><small>{today.new ? `知识库还有 ${today.new} 条未学` : '随时收录新的知识'}</small></div>
        <div><strong>{today.reviews}<em> / {user.preferences.daily_goal}</em></strong><span>今日已完成</span><small>{today.minutes ? `已专注 ${today.minutes} 分钟` : '每一次回忆都算数'}</small></div>
      </div>
      <div className="plan-progress" role="progressbar" aria-label="今日复习目标" aria-valuemin={0} aria-valuemax={user.preferences.daily_goal} aria-valuenow={Math.min(today.reviews, user.preferences.daily_goal)}><span style={{ width: `${progress * 100}%` }}/></div>
      <div className="plan-bottom">
        <div className="plan-actions">{ready > 0 ? <Link to="/review" className="button cream">开始今日复习<ArrowRight size={17}/></Link> : <button className="button cream" onClick={() => edit()}><Plus size={17}/>{data.totals.items ? '记录新知' : '记录第一条知识'}</button>}
          <span>{ready ? '先复习到期内容，再学新知' : today.new ? '今日新学额度已用完，可在设置中调整' : today.later_today ? `稍后还有 ${today.later_today} 条到期` : progress >= 1 ? <><Check size={14}/>今日目标已完成</> : data.totals.items ? '目前没有到期任务' : '从一个知识点或一道错题开始'}</span>
        </div>
        <Link to="/settings" className="plan-settings"><Settings2 size={14}/>调整目标</Link>
      </div>
    </section>

    <section className="subject-review-section" aria-label="按科目复习">
      <SectionTitle title="按科目开始" note="每日新学额度三科共用"/>
      <div className="subject-review-grid">{subjects.map(subject => {
        const summary = data.subjects.find(value => value.subject === subject.id)!
        const newCount = Math.min(today.new_available, summary.new)
        const available = summary.due + newCount
        return <article className={`subject-review-card ${subject.color}`} key={subject.id}>
          <span className="subject-review-symbol" aria-hidden="true">{subject.symbol}</span>
          <div className="subject-review-copy"><Link to={`/library?subject=${subject.id}`}><h3>{subject.name}</h3><ChevronRight size={13}/></Link><p><b>{summary.due}</b> 待复习<span>·</span><b>{summary.new}</b> 未学{summary.overdue > 0 && <small>{summary.overdue} 条逾期</small>}</p></div>
          {available ? <Link className="subject-review-start" to={`/review?subject=${subject.id}`} aria-label={`开始${subject.name}复习`}>开始<ArrowRight size={16}/></Link> : <button className="subject-review-start subject-review-add" onClick={() => edit({ subject: subject.id })} aria-label={`录入${subject.name}知识`}>录入<Plus size={16}/></button>}
        </article>
      })}</div>
    </section>

    <div className="metric-grid"><div className="metric"><span className="metric-icon sage"><BookOpen size={19}/></span><div><span>知识积累</span><strong>{data.totals.items}<small>条</small></strong></div><span className="metric-caption">属于你的知识花园</span></div><div className="metric"><span className="metric-icon clay"><Flame size={19}/></span><div><span>连续积累</span><strong>{data.totals.streak}<small>天</small></strong></div><span className="metric-caption">今天也为自己向前一步</span></div><div className="metric"><span className="metric-icon blue"><Clock3 size={19}/></span><div><span>累计专注</span><strong>{data.totals.minutes}<small>分钟</small></strong></div><span className="metric-caption">每次认真，都不会白费</span></div></div>
    <div className="dashboard-bottom">
      <section className="panel recent-panel"><SectionTitle title="最近拾起的知识" to="/library"/>{data.recent_items.length ? <div className="recent-list">{data.recent_items.map(item => <Link to={`/items/${item.id}`} key={item.id}><span className={`recent-subject ${subjects.find(subject => subject.id === item.subject)?.color}`}>{subjects.find(subject => subject.id === item.subject)?.symbol}</span><div><h3>{item.title}</h3><p>{subjectName(item.subject)}<span>·</span>{plainText(item.question) || '图片题目'}</p></div><span className="recent-date">{dateLabel(item.updated_at)}</span><ChevronRight size={16}/></Link>)}</div> : <Empty title="这里会留下你的积累" description="从一个你想真正记住的知识点开始。" action={<button className="text-button" onClick={() => edit()}>记录新知<ArrowRight size={15}/></button>}/>}</section>
      <section className="panel growth-panel"><SectionTitle title="一点点，长成习惯" note="近 13 周"/><Heatmap days={data.heatmap}/><div className="heatmap-caption"><span>每一格，都是认真过的日子</span><div>少 <i className="level-0"/><i className="level-1"/><i className="level-3"/><i className="level-4"/> 多</div></div><div className="growth-note"><Sprout size={20}/><p>{data.totals.active_days ? <>已经有 <strong>{data.totals.active_days}</strong> 个日子，<br/>你为未来的自己种下了答案。</> : <>不用等待完美的开始。<br/>今天，就可以是第一格。</>}</p></div></section>
    </div>
    <div className="bottom-note"><span><Sparkles size={15}/>{examDays !== null ? `距离你的目标日还有 ${examDays} 天，按自己的节奏向前。` : '记忆会淡，认真留下的痕迹不会。'}</span><span>KEEP GOING, KEEP GROWING <Leaf size={13}/></span></div>
  </div>
}
