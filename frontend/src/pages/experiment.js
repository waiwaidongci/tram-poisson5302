import {feedback, field} from '../components/common/fields.js';
import {empty, metrics, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {EXPERIMENT_STATUS} from '../constants/enums.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date, value} from '../utils/format.js';

function conclusionPanel(job) {
  const result = job.result;
  if (!result) {
    return panel('置换检验结论', p(job.status === 'failed' ? (job.error || '重算失败') : '尚未上传对账记录，暂无结论。', 'feedback'));
  }
  const stats = result.stats;
  return panel('整组置换检验结论',
    p(result.headline, 'intro-copy'),
    p(result.note, 'subtle'),
    metrics([
      {label:'纳入配对', value:stats.included_pairs, detail:`排除 ${stats.excluded_pairs} 对`},
      {label:'旧方案阻断率', value:stats.old_rate, detail:'次／百车次'},
      {label:'新方案阻断率', value:stats.new_rate, detail:'次／百车次'},
      {label:'阻断率差（旧−新）', value:stats.observed_difference, detail:stats.reduces_blockage ? '正值：新方案阻断更少' : '非正：未见减少'},
      {label:'置换 p 值', value:stats.p_value, detail:stats.method},
    ]),
    panel('各配对每百车次阻断率', table([
      {key:'pair_id', label:'配对'},
      {label:'旧方案率', render:row=>value(row.old_rate)},
      {label:'新方案率', render:row=>value(row.new_rate)},
      {label:'旧−新', render:row=>value(row.difference)},
    ], stats.per_pair, {caption:'各配对每百车次阻断率'})));
}

function registerForm(refresh) {
  const message = feedback();
  const submit = button('登记抽签单', {type:'submit', class:'primary', 'data-testid':'register-experiment'});
  return el('form', {class:'fields', onSubmit:handler(submit, message, async event => {
    const data = new FormData(event.target);
    const file = data.get('draw_csv');
    if (!file?.size) throw new Error('请选择抽签单 CSV');
    if (file.size > 3_500_000) throw new Error('抽签单 CSV 最多 3.5 MB');
    const item = await workspace.registerExperiment({
      name:data.get('name'), draw_csv:await file.text(),
      warmup_minutes:Number(data.get('warmup_minutes')),
      permutations:Number(data.get('permutations')),
    });
    await refresh();
    location.hash = `#experiment/${item.id}`;
  })},
    field({key:'name', label:'试验名称', type:'string', max_length:120}, '信号方案配对试验'),
    field({key:'warmup_minutes', label:'切换后热身时长（分钟，不计入）', type:'int', min:0, max:240}, 30),
    field({key:'permutations', label:'置换次数（20 对以内自动精确枚举）', type:'int', min:99, max:99999}, 9999),
    el('label', {class:'field', for:'draw_csv'}, el('span',{},'抽签单 CSV'),
      el('input', {id:'draw_csv', name:'draw_csv', type:'file', accept:'.csv,text/csv', required:true})),
    el('div', {class:'actions'},
      button('下载抽签单模板', {class:'quiet', type:'button', onClick:()=>
        workspace.download('/experiments/draw-template', 'draw-template.csv')}), submit),
    message);
}

export async function experimentPage(route, refresh) {
  const {experiments} = workspace;
  const id = route.id || experiments[0]?.id;
  if (!id) {
    return panel('信号方案配对试验',
      p('相邻路口同组、每对班次抽签决定新旧方案顺序。上传抽签单后再导入跨系统对账记录。', 'subtle'),
      session.canWrite ? registerForm(refresh) : p('只读角色可在登记后查看试验结论。', 'empty'),
      empty('还没有试验。', '#inputs', '查看台账'));
  }
  const job = await workspace.getExperiment(id);
  const message = feedback();
  const reconSubmit = button('上传对账并重算', {type:'submit', class:'primary', 'data-testid':'upload-recon'});
  const reconForm = session.canWrite && el('form', {class:'fields', onSubmit:handler(reconSubmit, message, async event => {
    const data = new FormData(event.target);
    const file = data.get('recon_csv');
    if (!file?.size) throw new Error('请选择对账记录 CSV');
    if (file.size > 3_500_000) throw new Error('对账 CSV 最多 3.5 MB');
    await workspace.uploadRecon(job.id, {recon_csv:await file.text(), reason:data.get('reason') || 'source-refresh'});
    await refresh();
  })},
    field({key:'reason', label:'本次更新说明', type:'string', required:false, max_length:80}, 'source-refresh'),
    el('label', {class:'field', for:'recon_csv'}, el('span',{},'过车与阻断对账 CSV'),
      el('input', {id:'recon_csv', name:'recon_csv', type:'file', accept:'.csv,text/csv', required:true})),
    el('div', {class:'actions'},
      button('下载对账模板', {class:'quiet', type:'button', onClick:()=>
        workspace.download('/experiments/recon-template', 'recon-template.csv')}),
      reconSubmit),
    p('重算前会先撤下当前有效结论并留痕；任一班缺窗则整对不纳入，切换后热身窗自动剔除。', 'subtle'),
    message);
  const picker = el('label', {class:'field run-picker', for:'exp-picker'}, el('span',{},'切换试验'),
    el('select', {id:'exp-picker', onChange:event=>{location.hash=`#experiment/${event.target.value}`;}},
      (experiments.some(item=>item.id===job.id) ? experiments : [job,...experiments])
        .map(item=>el('option',{value:item.id, selected:item.id===job.id}, item.name))));
  const list = table([
    {label:'试验', render:item=>link(item.name, `#experiment/${item.id}`)},
    {label:'状态', render:item=>pill(EXPERIMENT_STATUS[item.status], item.status)},
    {label:'纳入/配对', render:item=>`${item.included_count} / ${item.pair_count}`},
    {label:'更新时间', render:item=>date(item.updated_at)},
  ], experiments, {caption:'试验记录', empty:'首次登记后在此显示。'});
  return el('div', {},
    el('div', {class:'two-col'},
      el('div', {class:'wide-panel'},
        panel(job.name, pill(EXPERIMENT_STATUS[job.status], job.status),
          p(`热身 ${job.warmup_minutes} 分钟 · 对账指纹 ${(job.recon_checksum || '尚未对账').slice(0,16)}`, 'subtle'),
          conclusionPanel(job),
          link('查看风险页（哪对没纳入、缺了什么）', `#risk/${job.id}`, {class:'quiet'}),
          link('查看结论撤下/重算历史', `#conclusions/${job.id}`, {class:'quiet'})),
        reconForm && panel('源数据更新与重算', reconForm)),
      el('aside', {class:'sidebar-panel'},
        panel('切换试验', picker),
        panel('试验记录', list),
        panel('试验口径', el('ul', {class:'method-list'}, [
          '相邻路口同组，每对班次抽签确定旧/新方案顺序。',
          '过车量与阻断记录按抽签单跨系统对账。',
          '切换后半小时为热身窗，不计入任何方案。',
          '任一班缺窗，整对不纳入。',
          '置换检验只整组交换两班标签，重算每百车次阻断差。',
          '源数据更新先撤下旧结论再重算；原阻断预测照常使用。',
        ].map(text=>el('li',{},text)))))));
}
