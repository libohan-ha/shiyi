import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { dateLabel, subjectName } from '../lib'
import type { Stats } from '../types'
import './learning-outcomes.css'

export default function LearningOutcomes({ data, compact = false }: { data: Stats; compact?: boolean }) {
  const { today, learning } = data
  return <>
    <section className="panel learning-outcomes" aria-label="今日复盘收获">
      <div className="section-title"><h2>今日复盘收获</h2>{compact ? <Link to="/statistics">查看具体内容<ArrowRight size={14}/></Link> : <span>以实际记录为准</span>}</div>
      <dl className="outcome-metrics">
        <div><dt>已用时间</dt><dd><strong data-metric="minutes">{today.minutes}</strong><span>分钟</span></dd></div>
        <div><dt>不同任务</dt><dd><strong data-metric="unique">{today.unique_items}</strong><span>条</span></dd></div>
        <div><dt>薄弱任务覆盖</dt><dd><strong>{today.weak_points_covered}</strong><span>条</span></dd></div>
        <div><dt>整题独立完成</dt><dd><strong>{learning.problems_completed}</strong><span>/ {learning.problems_attempted} 道</span></dd></div>
      </dl>
      <p className="outcome-note">同一任务重复复习只计一条覆盖。整题按今天最后一次明确反馈统计；旧记录未填写的不推断为成功或失败。用时仅含已保存评分的专注时间，不设时长限制。</p>
    </section>
    {!compact && <section className="learning-details" aria-label="学习结果明细">
      <div className="panel outcome-detail">
        <div className="section-title"><h2>隔开一天，还能想起多少？</h2><span>近 30 天</span></div>
        <div className="delayed-result"><strong>{learning.delayed_retention === null ? '—' : `${Math.round(learning.delayed_retention * 100)}%`}</strong><p>{learning.delayed_reviews ? `${learning.delayed_successes} / ${learning.delayed_reviews} 次跨日首答成功` : '尚无跨日首答记录'}</p></div>
        <p className="outcome-note">按学习时区，每题每天只取首次评分，且上次复习在更早的日期；排除初学、同日重复和撤销。困难也算回忆成功，不等同于考试得分或整题完成率。</p>
        <h3>最近一次跨日首答仍未想起</h3>
        {learning.delayed_failures.length ? <ul className="outcome-list">{learning.delayed_failures.map(item => <li key={item.id}><Link to={`/items/${item.id}`}><span><strong>{item.title}</strong><small>{subjectName(item.subject)} · 间隔 {item.elapsed_days} 个学习日 · {dateLabel(item.reviewed_at)}</small>{item.blocker && <p>主要卡点：{item.blocker}</p>}</span><ArrowRight size={15}/></Link></li>)}</ul> : <p className="outcome-empty">暂无记录；同日刚练会不会覆盖这里的跨日表现。</p>}
        {learning.delayed_failure_count > 10 && <p className="outcome-note">共 {learning.delayed_failure_count} 条，展示最近 10 条。</p>}
      </div>
      <div className="panel outcome-detail">
        <div className="section-title"><h2>今天覆盖的薄弱任务</h2><span>{today.weak_points_covered} 条</span></div>
        {learning.covered_weak_points.length ? <ul className="outcome-list">{learning.covered_weak_points.map(item => <li key={item.id}><Link to={`/items/${item.id}`}><span><strong>{item.title}</strong><small>{subjectName(item.subject)} · 从原题提炼的小任务</small></span><ArrowRight size={15}/></Link></li>)}</ul> : <p className="outcome-empty">复习从原题提炼的小任务后，这里会显示具体覆盖内容。</p>}
        {today.weak_points_covered > 10 && <p className="outcome-note">展示其中 10 条；覆盖表示练过，不代表已经掌握。</p>}
        <h3>今天的整题表现</h3>
        {learning.problem_results.length ? <ul className="outcome-list">{learning.problem_results.map(item => <li key={item.id}><Link to={`/items/${item.id}`}><span><strong>{item.title}</strong><small>{item.independent_completed ? '已独立完成' : '尚未独立完成'} · {dateLabel(item.reviewed_at, true)}</small>{item.blocker && <p>主要卡点：{item.blocker}</p>}</span><ArrowRight size={15}/></Link></li>)}</ul> : <p className="outcome-empty">整题复习时明确记录是否独立完成，这里才会出现结果。</p>}
        {learning.problems_attempted > 10 && <p className="outcome-note">共 {learning.problems_attempted} 道，展示最近 10 道。</p>}
      </div>
    </section>}
  </>
}
