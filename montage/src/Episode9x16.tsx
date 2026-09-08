/**
 * Эпизод в вертикальном формате для шортсов.
 *
 * Холст 1080×1920. Форма исходника решает раскладку (`shortsBox`):
 *
 * - горизонтальный или квадратный кадр вписывается по ширине и стоит по центру,
 *   а равные поля сверху и снизу становятся полосами под баннер и субтитры;
 * - вертикальный кадр занимает весь экран, и текст ложится ПОВЕРХ него — иначе
 *   полос не остаётся и оформление исчезает целиком.
 *
 * Поля — сплошной цвет, а не размытая копия кадра: у плоского мультипликационного
 * стиля размытие выглядит грязно.
 *
 * Оформление работает без единой строчки настройки — баннер и палитра приходят
 * с дефолтами из `project.json` (см. `factory.montage.shorts_settings`).
 */
import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile} from 'remotion';
import '@fontsource/onest/cyrillic-400.css';
import '@fontsource/onest/cyrillic-600.css';
import '@fontsource/onest/cyrillic-700.css';
import {AudioBed} from './AudioBed';
import {Captions} from './Captions';
import {StillsTrack} from './StillsTrack';
import {CANVAS_WIDTH, shortsBox} from './shortsBox';
import type {Band} from './shortsBox';
import type {EpisodeProps} from './episodeMetadata';

/** Затемнение под текстом. Нужно только когда текст лежит на кадре. */
const Scrim: React.FC<{band: Band; from: 'top' | 'bottom'}> = ({band, from}) => (
	<div
		style={{
			position: 'absolute',
			top: band.top - (from === 'top' ? band.top : 80),
			left: 0,
			width: CANVAS_WIDTH,
			height: band.height + band.top * (from === 'top' ? 1 : 0) + 160,
			background:
				from === 'top'
					? 'linear-gradient(to bottom, rgba(0,0,0,0.75), rgba(0,0,0,0))'
					: 'linear-gradient(to top, rgba(0,0,0,0.8), rgba(0,0,0,0))',
			pointerEvents: 'none',
		}}
	/>
);

export const Episode9x16: React.FC<EpisodeProps> = ({
	layout,
	duck,
	shorts,
	captions,
}) => {
	if (!layout) return null;
	const box = shortsBox(layout.width, layout.height);
	const overlay = box.mode === 'fullscreen';

	return (
		<AbsoluteFill style={{backgroundColor: shorts.background}}>
			<div
				style={{
					position: 'absolute',
					top: box.videoTop,
					left: 0,
					width: CANVAS_WIDTH,
					height: box.videoHeight,
					overflow: 'hidden',
				}}
			>
				{/* Режим кадров: отрезков нет вовсе, картинку держат кадры.
				    Раньше здесь была только раскладка отрезков, и познавательный
				    шортс — жанр, у которого `stills` стоит режимом по умолчанию, —
				    выходил ВООБЩЕ БЕЗ картинки: баннер и субтитры на пустом фоне
				    (дымовой прогон 2026-09-08). */}
				{layout.mode === 'stills' ? (
					<StillsTrack
						stills={layout.stills}
						settings={layout.stillsSettings}
						fps={layout.fps}
					/>
				) : null}
				{layout.segments.map((segment) => (
					<Sequence
						key={segment.n}
						from={segment.from}
						durationInFrames={segment.durationInFrames}
					>
						{/* muted — по той же причине, что в 16:9: у выдачи модели своя
						    aac-дорожка, звук эпизода приходит из сведённых дорожек. */}
						<OffthreadVideo
							src={staticFile(segment.file)}
							muted
							style={{width: '100%', height: '100%', objectFit: 'cover'}}
						/>
					</Sequence>
				))}
			</div>

			{overlay ? <Scrim band={box.bannerBand} from="top" /> : null}
			{overlay ? <Scrim band={box.captionBand} from="bottom" /> : null}

			<div
				style={{
					position: 'absolute',
					top: box.bannerBand.top,
					left: 0,
					width: CANVAS_WIDTH,
					height: box.bannerBand.height,
					display: 'flex',
					alignItems: 'center',
					justifyContent: 'center',
				}}
			>
				<div
					style={{
						maxWidth: '84%',
						textAlign: 'center',
						fontFamily: 'Onest, sans-serif',
						fontWeight: 700,
						fontSize: 68,
						lineHeight: 1.15,
						color: shorts.accent,
						textShadow: overlay ? '0 2px 24px rgba(0,0,0,0.9)' : 'none',
					}}
				>
					{shorts.banner}
				</div>
			</div>

			{/* Флаг листа, а не «в шортсе всегда»: жанр может их и запретить. */}
			{captions === false ? null : (
				<Captions
					voice={layout.voice}
					band={box.captionBand}
					overlay={overlay}
				/>
			)}
			<AudioBed layout={layout} duck={duck} />
		</AbsoluteFill>
	);
};
