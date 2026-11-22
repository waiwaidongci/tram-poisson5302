export const ROLE = {admin:'复核主管', analyst:'分析员', viewer:'只读查看'};
export const STATUS = {queued:'排队中', running:'正在计算', complete:'计算完成', failed:'运行失败'};
export const REVIEW = {pending:'待复核', accepted:'已通过', returned:'已退回'};
export const EXPERIMENT_STATUS = {
  draft:'待对账', stale:'结论已撤下', computed:'结论有效', failed:'重算失败',
};
export const CONCLUSION_STATE = {active:'当前有效', superseded:'已撤下'};
export const SOURCE_SYSTEM = {signal:'信号系统过车', duty:'值班系统阻断'};
