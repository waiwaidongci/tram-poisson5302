import {panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {CONCLUSION_STATE} from '../constants/enums.js';
import {workspace} from '../stores/workspace.js';
import {el, link, p} from '../utils/dom.js';
import {date, value} from '../utils/format.js';

export async function conclusionsPage(route) {
  const id = route.id || workspace.experiments[0]?.id;
  if (!id) return panel('结论历史', p('还没有试验，请先在配对试验页登记抽签单。', 'empty'),
    link('前往信号方案配对试验', '#experiment', {class:'quiet'}));
  const [job, items] = await Promise.all([
    workspace.getExperiment(id), workspace.experimentConclusions(id)]);
  return el('div', {}, panel(`${job.name} · 结论撤下与重算历史`,
    p('每次源数据更新都会先把当前有效结论置为「已撤下」再重算，旧结论的输入指纹与统计量完整保留。', 'subtle'),
    table([
      {key:'version', label:'版本'},
      {label:'状态', render:row=>pill(CONCLUSION_STATE[row.state], row.state)},
      {label:'纳入/排除', render:row=>`${row.included_pairs} / ${row.excluded_pairs}`},
      {label:'阻断率差（旧−新）', render:row=>value(row.observed_difference)},
      {key:'p_value', label:'置换 p 值'},
      {key:'reason', label:'撤下/重算原因'},
      {key:'author', label:'操作者'},
      {label:'生成时间', render:row=>date(row.created_at)},
      {label:'撤下时间', render:row=>date(row.superseded_at)},
    ], items, {caption:'结论版本', empty:'还没有产生过结论。'})),
    panel('输入指纹核对', el('ul', {class:'method-list'}, items.map(row=>el('li', {},
      `v${row.version} · 抽签单 ${row.draw_checksum.slice(0,12)}… · 对账 ${row.recon_checksum.slice(0,12)}… · ${row.headline}`)))),
    panel('回查', link('返回试验结论', `#experiment/${id}`, {class:'quiet'}),
      link('打开风险页', `#risk/${id}`, {class:'quiet'})));
}
