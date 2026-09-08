/**
 * Звуковые слои эпизода: речь, SFX и музыка с приглушением под ними.
 *
 * Громкости перенесены из mix_audio.py вместе с их обоснованием и лежат в
 * монтажном листе (`volume` каждой единицы): речь 1.0, SFX 0.7, музыка 0.35.
 * Музыка — единственная дорожка с переменной громкостью.
 */
import React, {useMemo} from 'react';
import {Audio, Sequence, staticFile, useVideoConfig} from 'remotion';
import {duckingOptions, musicVolumeAtFrame} from './ducking';
import type {Interval} from './ducking';
import {envelopeVolumeAtFrame, staticTrackVolume} from './envelope';
import type {Layout, PlacedAudio} from './metadata';

type Duck = {gain: number; attackMs: number; releaseMs: number};

const StaticTrack: React.FC<{entry: PlacedAudio}> = ({entry}) => {
	const {fps} = useVideoConfig();
	const volume = staticTrackVolume(entry.volume, entry.envelope, fps);
	return (
		<Sequence from={entry.from} durationInFrames={entry.durationInFrames}>
			<Audio src={staticFile(entry.file)} volume={volume} />
		</Sequence>
	);
};

/** Дорожка, уступающая речи: музыка и подложка ведут себя одинаково. */
const DuckedTrack: React.FC<{
	entry: PlacedAudio;
	intervals: Interval[];
	duck: Duck;
}> = ({entry, intervals, duck}) => {
	const {fps} = useVideoConfig();
	const opts = useMemo(
		() => duckingOptions(duck, entry.volume, fps),
		[duck, entry.volume, fps],
	);
	return (
		<Sequence from={entry.from} durationInFrames={entry.durationInFrames}>
			<Audio
				src={staticFile(entry.file)}
				// Кадр внутри Sequence отсчитывается от её начала, а интервалы речи
				// заданы в абсолютных кадрах эпизода — поэтому смещение возвращается.
				// Огибающая и приглушение ПЕРЕМНОЖАЮТСЯ: первая — авторское движение
				// уровня, второе — служебное освобождение места под речь; выбрать
				// одно из двух значило бы потерять либо замысел, либо разборчивость.
				volume={(frame) => {
					const ducked = musicVolumeAtFrame(frame + entry.from, intervals, opts);
					return entry.envelope
						? (ducked * envelopeVolumeAtFrame(frame, entry.envelope, 1, fps))
						: ducked;
				}}
			/>
		</Sequence>
	);
};

export const AudioBed: React.FC<{
	layout: Layout;
	duck: Duck;
}> = ({layout, duck}) => {
	// Приглушение вызывает ТОЛЬКО речь. Пока в этот список входили и эффекты,
	// шестидесятисекундная подложка моря держала музыку приглушённой весь
	// эпизод, а сама не уступала ничему — речи под ней было не слышно (живой
	// прогон 2026-09-05). Освобождать место надо под слова, а не под шум.
	const intervals: Interval[] = useMemo(
		() =>
			layout.voice.map((entry) => ({
				from: entry.from,
				to: entry.from + entry.durationInFrames,
			})),
		[layout.voice],
	);

	return (
		<>
			{layout.voice.map((entry) => (
				<StaticTrack key={`v-${entry.id}`} entry={entry} />
			))}
			{layout.sfx.map((entry) => (
				<StaticTrack key={`s-${entry.id}`} entry={entry} />
			))}
			{layout.foley.map((entry) => (
				<StaticTrack key={`f-${entry.id}`} entry={entry} />
			))}
			{layout.music.map((entry) => (
				<DuckedTrack
					key={`m-${entry.id}`}
					entry={entry}
					intervals={intervals}
					duck={duck}
				/>
			))}
			{layout.ambience.map((entry) => (
				<DuckedTrack
					key={`a-${entry.id}`}
					entry={entry}
					intervals={intervals}
					duck={duck}
				/>
			))}
		</>
	);
};
