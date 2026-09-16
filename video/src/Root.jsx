import React from 'react';
import {Composition} from 'remotion';
import {DURATION, FPS} from './theme';
import {Summary} from './Summary';

/* Placeholder data only; the server passes the real run through --props. */
const sample = (kind) => ({
  kicker: kind === 'radar' ? 'Track A, reputation radar' : 'Track B, prospect diagnostic',
  title: kind === 'radar' ? 'Weekly brief' : 'Prospect diagnostic',
  subtitle: 'Run this with real data through the app',
  runLine: 'growpido.up.railway.app',
  meterKicker: 'The result',
  meterTitle: 'Nothing rendered yet',
  meter: [{label: 'verified', n: 1, color: '#8fd9a8'}, {label: 'partial', n: 1, color: '#e8c46a'}, {label: 'refused', n: 1, color: '#f08a8a'}],
  meterNote: '',
  bodyKicker: 'Summary',
  body: ['Pass real props to see the summary here.'],
  itemsKicker: 'Three biggest gaps',
  items: [{title: 'Gap one', note: 'note'}],
  refusedKicker: 'One claim the system refused',
  refused: {claim: 'A claim', reason: 'why it failed'},
  signoff: {kicker: 'Human gate', title: 'Draft, waiting for a named approver', note: ''},
  footer: 'LinkedIn is never fetched. Nothing leaves without a named approver.',
});

export const Root = () => (
  <>
    <Composition id="TrackB" component={Summary} durationInFrames={DURATION} fps={FPS} width={1280} height={720} defaultProps={{data: sample('diagnostic')}} />
    <Composition id="TrackA" component={Summary} durationInFrames={DURATION} fps={FPS} width={1280} height={720} defaultProps={{data: sample('radar')}} />
  </>
);
