/**
 * Эпизод в исходном формате: отрезки встык, как это делала склейка на ffmpeg.
 *
 * Видео подключается ТОЛЬКО с `muted`. У каждой выдачи видеомодели есть своя
 * aac-дорожка (проверено на четырёх живых файлах, knowledge/remotion.md), и
 * прежняя сборка её сознательно выбрасывала фильтром `concat=n=N:v=1:a=0` —
 * звук эпизода приходит из сведённых дорожек, а не из модели. `OffthreadVideo`
 * по умолчанию играет звук файла, поэтому без `muted` звук модели тихо
 * просочился бы поверх сведённого.
 */
import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile} from 'remotion';
import '@fontsource/onest/cyrillic-400.css';
import '@fontsource/onest/cyrillic-600.css';
import {AudioBed} from './AudioBed';
import {Captions} from './Captions';
import {StillsTrack} from './StillsTrack';
import {WIDE_CAPTION_BAND} from './shortsBox';
import type {EpisodeProps} from './episodeMetadata';

export const Episode16x9: React.FC<EpisodeProps> = ({layout, duck, captions}) => {
	if (!layout) return null;

	// Субтитры включает КАРТОЧКА ЖАНРА, а не композиция: у познавательного в ней
	// стоит `always`, и раньше это обещание не исполнялось — 16:9 не умел их
	// вовсе. Полей у горизонтального кадра нет, поэтому текст всегда поверх.
	const subs = captions ? (
		<Captions voice={layout.voice} band={WIDE_CAPTION_BAND} overlay />
	) : null;

	// Режим кадров: отрезков нет вовсе, эпизод держится на кадрах под озвучку.
	if (layout.mode === 'stills') {
		return (
			<AbsoluteFill style={{backgroundColor: 'black'}}>
				<StillsTrack
					stills={layout.stills}
					settings={layout.stillsSettings}
					fps={layout.fps}
				/>
				{subs}
				<AudioBed layout={layout} duck={duck} />
			</AbsoluteFill>
		);
	}

	return (
		<AbsoluteFill style={{backgroundColor: 'black'}}>
			{layout.segments.map((segment) => (
				<Sequence
					key={segment.n}
					from={segment.from}
					durationInFrames={segment.durationInFrames}
				>
					<OffthreadVideo src={staticFile(segment.file)} muted />
				</Sequence>
			))}
			{subs}
			<AudioBed layout={layout} duck={duck} />
		</AbsoluteFill>
	);
};
