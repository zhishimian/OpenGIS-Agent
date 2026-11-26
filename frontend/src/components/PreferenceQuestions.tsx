import type { StudioPreferences } from "../types/studio";

export const initialPreferences: StudioPreferences = {
  north_style: "compass_star", scale_style: "cartographic", label_language: "随任务",
  basemap: "offline", execution_policy: "auto",
};

type Choice<T extends string> = readonly [T, string];
function Choices<T extends string>({ question, options, current, select, symbol }: {
  question: string; options: ReadonlyArray<Choice<T>>; current: T; select: (v: T) => void;
  symbol?: "north" | "scale";
}) {
  return <fieldset>
    <legend className="mb-2 text-sm font-semibold text-slate-800">{question}</legend>
    <div className="flex flex-wrap gap-2">{options.map(([id, label]) =>
      <label key={id} className={`relative cursor-pointer rounded-lg border px-3 py-2 text-center text-sm has-[:focus-visible]:ring-2 ${current === id ? "bg-sky-50 border-sky-600 text-sky-800" : "border-slate-200 text-slate-700"} ${symbol ? "flex-1" : ""}`}>
        <input type="radio" className="sr-only" name={question} checked={current === id} onChange={() => select(id)} />
        {symbol === "north" && <span aria-hidden className="symbol-sample" data-north={id}><i className="north-shape" /></span>}
        {symbol === "scale" && <span aria-hidden className="symbol-sample" data-scale={id}><i className="scale-shape">10 km</i></span>}
        {label}
      </label>
    )}</div>
  </fieldset>;
}

export function PreferenceQuestions({ step, value, onChange }: {
  step: number; value: StudioPreferences; onChange: (v: StudioPreferences) => void;
}) {
  function field<K extends keyof StudioPreferences>(key: K, question: string,
    options: ReadonlyArray<Choice<StudioPreferences[K]>>, symbol?: "north" | "scale") {
    return <Choices question={question} options={options} current={value[key]} symbol={symbol}
      select={v => onChange({ ...value, [key]: v })} />;
  }
  return <div className="space-y-5 p-5">
    {step === 1 ? <>
      {field("north_style", "喜欢哪一种指北针？", [["compass_star", "罗盘星"], ["sleek_needle", "细针"], ["chevron", "人字箭头"], ["line_arrow", "线形箭头"]], "north")}
      {field("scale_style", "比例尺用哪种画法？", [["cartographic", "单排分段"], ["double_box", "双排方格"], ["ticked", "线式刻度"]], "scale")}
      {field("label_language", "成图的标题和标注用什么语言？", [["随任务", "随任务"], ["中文", "中文"], ["英文", "英文"], ["中英双语", "中英双语"]])}
    </> : <>
      {field("basemap", "打开地图时使用哪种底图？", [["offline", "离线空白"], ["positron", "浅色底图"], ["dark", "深色底图"], ["osm", "街道地图"]])}
      {field("execution_policy", "希望在哪一步参与确认？", [["auto", "由助手自动执行"], ["plan_first", "先确认分析方案"], ["step_review", "分阶段审阅结果"]])}
    </>}
  </div>;
}
