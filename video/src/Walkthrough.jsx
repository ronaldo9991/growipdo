import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {T} from './theme';

/* A five minute walkthrough of the live site. The picture is a real screen recording of
   growpido.up.railway.app, cut at the moments the walkthrough script marked. Nothing here is
   re-enacted: both runs in the footage are real runs that called the models.

   The recording keeps its own area and the words sit underneath it, so nothing on the page is
   ever covered by a caption. */

const STAGE = 612;
const STRIP = 720 - STAGE;

const Strip = ({label, text, total}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{
      position: 'absolute', left: 0, right: 0, bottom: 0, height: STRIP,
      background: T.bg, borderTop: `1px solid ${T.line}`,
      display: 'flex', alignItems: 'center', gap: 22, padding: '0 28px',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 9, flex: '0 0 auto', maxWidth: 250,
        fontFamily: T.sans, fontSize: 14, letterSpacing: 0.3, color: T.ink2,
      }}>
        <span style={{width: 7, height: 7, borderRadius: 999, background: T.ok, flex: '0 0 auto'}} />
        {label}
      </div>
      <div style={{
        flex: 1, minWidth: 0, fontFamily: T.sans, fontSize: 18, lineHeight: 1.36,
        color: T.ink, textAlign: 'center',
      }}>
        {text}
      </div>
      <div style={{flex: '0 0 auto', fontFamily: T.mono, fontSize: 12, color: T.ink3, textAlign: 'right'}}>
        growpido.up.railway.app
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 3, background: 'rgba(225,224,204,0.10)'}}>
        <div style={{width: `${Math.min(100, (frame / total) * 100)}%`, height: '100%', background: T.ink}} />
      </div>
    </div>
  );
};

export const Walkthrough = ({clip, cuts, total}) => {
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill style={{background: T.bg}}>
      {cuts.map((cut, i) => (
        <Sequence key={i} from={cut.from} durationInFrames={cut.len} name={cut.label}>
          <AbsoluteFill>
            <div style={{position: 'absolute', top: 0, left: 0, right: 0, height: STAGE, background: '#000'}}>
              <OffthreadVideo
                src={staticFile(clip)}
                startFrom={cut.srcFrom}
                style={{width: '100%', height: '100%', objectFit: 'contain'}}
              />
            </div>
            <Strip label={cut.label} text={cut.text || ''} total={total} />
            {cut.vo ? <Audio src={staticFile(`vo/${cut.vo}`)} /> : null}
          </AbsoluteFill>
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
