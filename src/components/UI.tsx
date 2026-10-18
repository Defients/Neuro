import React from "react";
export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <span className={"badge " + tone}>
      <i />
      {children}
    </span>
  );
}
export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={"panel " + className}>
      <div className="panel-heading">
        <div>
          {eyebrow && <span className="eyebrow">{eyebrow}</span>}
          <h3>{title}</h3>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
