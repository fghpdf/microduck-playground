import type { RunDiagnostics } from "./api";
import { useI18n } from "./i18n";
export default function Diagnostics({ data }: { data?: RunDiagnostics }) {
  const { t } = useI18n();
  if (!data)
    return (
      <section className="diagnostics">
        <h2>{t("运行诊断")}</h2>
        <p>{t("此记录没有诊断数据")}</p>
      </section>
    );
  const latest = data.health.at(-1);
  const loop = latest?.result?.control_loop;
  const measured = loop?.achieved_hz;
  const target = loop?.target_hz ?? 50;
  const failures = data.commands.filter(
    (c) => c.accepted === false || !!c.error,
  ).length;
  const command = data.commands.at(-1);
  const slow = typeof measured === "number" && measured < target * 0.9;
  return (
    <section className="diagnostics" aria-label={t("运行诊断")}>
      <h2>
        {t("运行诊断")} <span>{t("控制服务实测 · 保存在本次记录中")}</span>
      </h2>
      <div className="diagnostic-metrics">
        <div>
          <small>{t("控制频率")}</small>
          <strong>
            {typeof measured === "number" ? measured.toFixed(1) : t("未知")} /{" "}
            {target} Hz
          </strong>
        </div>
        <div>
          <small>{t("网页 / API 指令")}</small>
          <strong>
            {data.commands.length} {t("次")} · {failures} {t("次失败")}
          </strong>
        </div>
        <div>
          <small>{t("最近指令往返")}</small>
          <strong>
            {command ? `${command.duration_ms.toFixed(1)} ms` : t("尚无指令")}
          </strong>
        </div>
      </div>
      {slow && (
        <p className="diagnostic-warning">
          {t("控制频率偏低，可能影响运动策略与运行结果。")}
        </p>
      )}
      {latest?.error && <p className="diagnostic-warning">{t(latest.error)}</p>}
      {latest?.result?.reason && (
        <p className="diagnostic-warning">{t(latest.result.reason)}</p>
      )}
      <p className="diagnostic-note">
        {t(
          "频率来自官方控制循环；延迟为本地桥接服务到官方控制服务的往返时间。直接通过官方 CLI 发送的指令不计入这里。",
        )}
      </p>
    </section>
  );
}
