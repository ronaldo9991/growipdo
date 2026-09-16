import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {T} from './theme';

/* Small helpers, all motion is gentle: nothing flies, things settle. */
export const useRise = (delay = 0) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - delay, fps, config: {damping: 200}});
  return {opacity: s, transform: `translateY(${interpolate(s, [0, 1], [14, 0])}px)`};
};

export const Frame = ({children, footer}) => (
  <div style={{
    position: 'absolute', inset: 0, background: T.bg, color: T.ink, fontFamily: T.sans,
    padding: '64px 72px', display: 'flex', flexDirection: 'column', justifyContent: 'center',
  }}>
    <div style={{position: 'absolute', inset: 24, border: `1px solid ${T.line}`, borderRadius: 28, pointerEvents: 'none'}} />
    {children}
    {footer ? (
      <div style={{position: 'absolute', left: 72, right: 72, bottom: 46, color: T.ink3, fontFamily: T.mono, fontSize: 18}}>{footer}</div>
    ) : null}
  </div>
);

export const Kicker = ({children, delay = 0}) => (
  <div style={{...useRise(delay), fontFamily: T.mono, fontSize: 20, letterSpacing: 3, textTransform: 'uppercase', color: T.ink3, marginBottom: 18}}>{children}</div>
);

export const Title = ({children, size = 76, delay = 4}) => (
  <div style={{...useRise(delay), fontSize: size, lineHeight: 1.05, letterSpacing: -1.5, fontWeight: 500}}>{children}</div>
);

export const Line = ({children, size = 28, color = T.ink2, delay = 10, mono = false, style = {}}) => (
  <div style={{...useRise(delay), fontSize: size, lineHeight: 1.45, color, fontFamily: mono ? T.mono : T.sans, marginTop: 14, ...style}}>{children}</div>
);

/* The same proportional bar the site shows, drawn over a second */
export const Meter = ({parts, delay = 8}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const grow = spring({frame: frame - delay, fps, config: {damping: 200}});
  const total = parts.reduce((t, p) => t + p.n, 0) || 1;
  return (
    <div style={{marginTop: 34}}>
      <div style={{display: 'flex', height: 18, borderRadius: 999, overflow: 'hidden', border: `1px solid ${T.line}`, background: T.panel}}>
        {parts.map((p, i) => (
          <div key={i} style={{width: `${(p.n / total) * 100 * grow}%`, background: p.color}} />
        ))}
      </div>
      <div style={{display: 'flex', gap: 34, marginTop: 20, flexWrap: 'wrap'}}>
        {parts.map((p, i) => (
          <div key={i} style={{...useRise(delay + 4 + i * 3), display: 'flex', alignItems: 'center', gap: 10, fontSize: 24, color: T.ink2}}>
            <span style={{width: 14, height: 14, borderRadius: 4, background: p.color, display: 'inline-block'}} />
            <b style={{color: T.ink, fontWeight: 600}}>{p.n}</b> {p.label}
          </div>
        ))}
      </div>
    </div>
  );
};

export const Card = ({children, tone = T.line, delay = 6, style = {}}) => (
  <div style={{
    ...useRise(delay), background: T.panel, border: `1px solid ${tone}`, borderRadius: 18,
    padding: '22px 26px', marginTop: 16, ...style,
  }}>{children}</div>
);

export const clamp = (text, words) => {
  const w = String(text || '').split(/\s+/).filter(Boolean);
  return w.length <= words ? w.join(' ') : w.slice(0, words).join(' ') + '...';
};
