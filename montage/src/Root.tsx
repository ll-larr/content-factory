import React from 'react';
import {Composition} from 'remotion';
import {Episode16x9} from './Episode16x9';
import {Episode9x16} from './Episode9x16';
import {calculateEpisodeMetadata, SHORTS_HEIGHT, SHORTS_WIDTH} from './episodeMetadata';
import type {EpisodeProps} from './episodeMetadata';

/**
 * Пустой лист для Studio без `--props`. Рендер всегда получает настоящий лист
 * из `scripts/render.py`, поэтому дефолты нужны только чтобы Studio открылась.
 */
const emptyList = (format: '16x9' | '9x16'): EpisodeProps => ({
	episode: 'ep00',
	format,
	segments: [],
	voice: [],
	sfx: [],
	music: [],
	duck: {gain: 0.5, attackMs: 120, releaseMs: 700},
	expected: {segments: 0, segmentSeconds: 0, tolerance: 0.05},
	shorts: {banner: '', background: '#101820', accent: '#E8B04B'},
	captions: format === '9x16',
});

export const RemotionRoot: React.FC = () => {
	return (
		<>
			<Composition
				id="Episode16x9"
				component={Episode16x9}
				defaultProps={emptyList('16x9')}
				calculateMetadata={calculateEpisodeMetadata}
				durationInFrames={1}
				fps={24}
				width={SHORTS_HEIGHT}
				height={SHORTS_WIDTH}
			/>
			<Composition
				id="Episode9x16"
				component={Episode9x16}
				defaultProps={emptyList('9x16')}
				calculateMetadata={calculateEpisodeMetadata}
				durationInFrames={1}
				fps={24}
				width={SHORTS_WIDTH}
				height={SHORTS_HEIGHT}
			/>
		</>
	);
};
