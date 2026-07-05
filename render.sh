#!/bin/sh
# Render a MIDI file to WAV with the adaptive-tuning synthesizer.
# usage: ./render.sh input.mid output-base [tuner]
if [ ! "${2}" ]
then
	echo "usage: ./render.sh input.mid output-base [tuner]" >&2
	exit 2
fi
tuner="${3:-stretch}"
# pypy3 renders several times faster than CPython; allow override via TUNING_PYTHON
python="${TUNING_PYTHON:-$(command -v pypy3 || echo python3)}"
time "${python}" "$(dirname "${0}")"/midi.py "${1}" "${2}" "${tuner}" || exit 1
sox -t raw -r 44100 -b 32 -c 2 -e signed-integer "${2}".raw "${2}".wav
echo "Wrote ${2}.wav" >&2
