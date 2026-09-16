import React from 'react';
import {AbsoluteFill, Sequence, useVideoConfig} from 'remotion';
import {T} from './theme';
import {Card, Frame, Kicker, Line, Meter, Title, clamp} from './parts';

/* One minute, six scenes. Every number shown here comes from the run's own ledger. */
export const Summary = ({data}) => {
  const {fps, durationInFrames} = useVideoConfig();
  const s = (sec) => Math.round(sec * fps);
  const scenes = [
    {from: 0, to: 6, el: (
      <Frame footer={data.runLine}>
        <Kicker>{data.kicker}</Kicker>
        <Title>{data.title}</Title>
        <Line size={30} delay={8}>{data.subtitle}</Line>
      </Frame>
    )},
    {from: 6, to: 16, el: (
      <Frame footer={data.runLine}>
        <Kicker>{data.meterKicker}</Kicker>
        <Title size={50}>{data.meterTitle}</Title>
        <Meter parts={data.meter} />
        {data.meterNote ? <Line size={24} delay={22} color={T.ink3}>{data.meterNote}</Line> : null}
      </Frame>
    )},
    {from: 16, to: 31, el: (
      <Frame footer={data.runLine}>
        <Kicker>{data.bodyKicker}</Kicker>
        {(data.body || []).map((p, i) => (
          <Line key={i} size={i === 0 ? 28 : 24} delay={6 + i * 12} color={i === 0 ? T.ink : T.ink2}>{p}</Line>
        ))}
      </Frame>
    )},
    {from: 31, to: 46, el: (
      <Frame footer={data.runLine}>
        <Kicker>{data.itemsKicker}</Kicker>
        {(data.items || []).slice(0, 3).map((it, i) => (
          <Card key={i} delay={6 + i * 12}>
            <div style={{fontSize: 27, fontWeight: 500}}>{i + 1}. {it.title}</div>
            {it.note ? <div style={{fontSize: 22, color: T.ink2, marginTop: 8, lineHeight: 1.4}}>{clamp(it.note, 28)}</div> : null}
          </Card>
        ))}
      </Frame>
    )},
    {from: 46, to: 54, el: (
      <Frame footer={data.runLine}>
        <Kicker>{data.refusedKicker}</Kicker>
        <Card tone={T.bad}>
          <div style={{fontSize: 26, lineHeight: 1.35}}>{clamp(data.refused && data.refused.claim, 34)}</div>
          <div style={{fontSize: 22, color: T.bad, marginTop: 12, lineHeight: 1.4}}>{clamp(data.refused && data.refused.reason, 30)}</div>
        </Card>
      </Frame>
    )},
    {from: 54, to: 60, el: (
      <Frame footer={data.footer}>
        <Kicker>{data.signoff.kicker}</Kicker>
        <Title size={46}>{data.signoff.title}</Title>
        {data.signoff.note ? <Line size={24} delay={10} color={T.ink2}>{clamp(data.signoff.note, 34)}</Line> : null}
      </Frame>
    )},
  ];
  return (
    <AbsoluteFill style={{background: T.bg}}>
      {scenes.map((sc, i) => (
        <Sequence key={i} from={s(sc.from)} durationInFrames={Math.min(s(sc.to) - s(sc.from), durationInFrames - s(sc.from))}>
          {sc.el}
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
