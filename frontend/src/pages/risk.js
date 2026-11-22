import {metrics, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {EXPERIMENT_STATUS, SOURCE_SYSTEM} from '../constants/enums.js';
import {workspace} from '../stores/workspace.js';
import {el, link, p} from '../utils/dom.js';
import {value} from '../utils/format.js';

function issueCell(issues) {
  if (!issues.length) return pill('已纳入', 'computed');
  return el('ul', {class:'method-list'}, issues.map(text=>el('li',{},text)));
}

function shiftCell(shifts) {
  return el('ul', {class:'method-list'}, shifts.map(shift => el('li', {},
    `${shift.shift_id}（${shift.scheme_order}，切换 ${shift.switch_at}）`,
    shift.missing_sources.length
      ? el('strong', {class:'feedback'}, ' 缺：' + shift.missing_sources.map(code=>SOURCE_SYSTEM[code]).join('、'))
      : el('span', {class:'subtle'}, ` · ${shift.record_count} 条记录`))));
}

export async function riskPage(route) {
  const id = route.id || workspace.experiments[0]?.id;
  if (!id) return panel('配对试验风险页', p('还没有试验，请先在配对试验页登记抽签单。', 'empty'),
    link('前往信号方案配对试验', '#experiment', {class:'quiet'}));
  const report = await workspace.experimentRisk(id);
  const excludedRows = report.excluded_pairs;
  return el('div', {},
    el('div', {class:'two-col'},
      el('div', {class:'wide-panel'},
        panel(report.name,
          pill(EXPERIMENT_STATUS[report.status], report.status),
          p(`热身窗 ${report.warmup_minutes} 分钟不计入；对账指纹 ${(report.recon_checksum || '尚无对账').slice(0,16)}。本页按当前对账快照实时计算，结论撤下期间也可查。`, 'subtle'),
          metrics([
            {label:'配对总数', value:report.pair_count},
            {label:'纳入', value:report.included_count, detail:'参与置换检验'},
            {label:'排除', value:report.excluded_count, detail:'任一班缺窗即整对不纳入'},
          ])),
        panel('未纳入配对与缺窗原因', table([
          {key:'pair_id', label:'配对编号'},
          {key:'group_name', label:'相邻路口同组'},
          {label:'班次与缺失来源', render:row=>shiftCell(row.shifts)},
          {label:'问题清单', render:row=>issueCell(row.issues)},
        ], excludedRows, {caption:'未纳入配对与缺窗原因', empty:'全部配对均已纳入，没有缺窗。'})),
        panel('全部配对对账明细', table([
          {key:'pair_id', label:'配对'},
          {key:'group_name', label:'同组'},
          {label:'是否纳入', render:row=>row.included ? pill('纳入','computed') : pill('排除','failed')},
          {label:'旧 阻断/车次', render:row=>`${row.old_blockage} / ${row.old_exposure}`},
          {label:'新 阻断/车次', render:row=>`${row.new_blockage} / ${row.new_exposure}`},
          {label:'热身剔除阻断', render:row=>value(row.warmup_blockage)},
        ], report.pairs, {caption:'全部配对对账明细'}))),
      el('aside', {class:'sidebar-panel'},
        panel('回查', link('返回试验结论', `#experiment/${id}`, {class:'quiet'}),
          link('查看结论历史', `#conclusions/${id}`, {class:'quiet'})),
        panel('排除口径', el('ul', {class:'method-list'}, [
          '过车量来自信号系统、阻断来自值班系统，缺任一来源即缺窗。',
          '记录超出抽签班次窗口或覆盖不全，标记为异常并排除整对。',
          '切换后热身期内的车次与阻断一律剔除。',
          '排除不影响其他配对，原阻断预测模型照常使用。',
        ].map(text=>el('li',{},text)))))));
}
