"use client";

type LocalTimeProps = {
  value: string;
  relative?: boolean;
};

const relativeLabel = (date: Date): string => {
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const absoluteSeconds = Math.abs(seconds);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (absoluteSeconds < 60) return formatter.format(seconds, "second");
  if (absoluteSeconds < 3600)
    return formatter.format(Math.round(seconds / 60), "minute");
  if (absoluteSeconds < 86400)
    return formatter.format(Math.round(seconds / 3600), "hour");
  return formatter.format(Math.round(seconds / 86400), "day");
};

export function LocalTime({ value, relative = false }: LocalTimeProps) {
  const date = new Date(value);
  const absolute = new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
  return (
    <time dateTime={value} title={absolute} suppressHydrationWarning>
      {relative ? relativeLabel(date) : absolute}
    </time>
  );
}
