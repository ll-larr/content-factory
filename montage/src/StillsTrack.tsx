/**
 * Кадры под озвучку: эпизод, собранный без единого отрезка.
 *
 * Кадр живёт столько, сколько говорит привязанная к нему реплика, и всё это
 * время медленно наезжает. Минута неподвижных картинок смотрится мёртвой, но и
 * заметное движение отвлекает от смысла, ради которого познавательный кадр
 * нарисован, — отсюда несколько процентов масштаба, а не эффектный пролёт.
 *
 * Картинка масштабируется с запасом (`SAFETY`): при наезде края уезжают за
 * пределы кадра, и без запаса по краям появилась бы чёрная полоса.
 *
 * Имя файла — StillsTrack, а не Stills: логика раскладки лежит в `stills.ts`, и
 * два файла, различающиеся только регистром, на Windows и macOS считаются одним.
 */
import React from 'react';
import {AbsoluteFill, Img, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {stillOpacity, stillZoom} from './stills';
import type {PlacedStill, StillsSettings} from './stills';

const SAFETY = 1.02;

const Still: React.FC<{
	still: PlacedStill;
	settings: StillsSettings;
	fps: number;
}> = ({still, settings, fps}) => {
	const frame = useCurrentFrame();
	const zoom = stillZoom(frame, still.durationInFrames, settings);
	const opacity = stillOpacity(frame, still.durationInFrames, settings, fps);

	return (
		<AbsoluteFill style={{backgroundColor: 'black', opacity}}>
			<Img
				src={staticFile(still.file)}
				style={{
					width: '100%',
					height: '100%',
					objectFit: 'cover',
					transform: `scale(${zoom * SAFETY})`,
				}}
			/>
		</AbsoluteFill>
	);
};

export const StillsTrack: React.FC<{
	stills: PlacedStill[];
	settings: StillsSettings;
	fps: number;
}> = ({stills, settings, fps}) => (
	<>
		{stills.map((still) => (
			<Sequence
				key={still.n}
				from={still.from}
				durationInFrames={still.durationInFrames}
			>
				<Still still={still} settings={settings} fps={fps} />
			</Sequence>
		))}
	</>
);
