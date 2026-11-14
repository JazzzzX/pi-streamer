/* LDAC round trip with the library that is in the image: encode a known two-tone stereo
 * signal into A2DP-style packets, decode them with the same call sequence as bluez-alsa's
 * a2dp-ldac.c, and compare the result with the original.
 * Usage: check-image-ldac <sample rate> <quality index: 0 = 990/909 kbps, 1 = 660/606, 2 = 330/303> <minimum dB> */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ldacBT.h>

#define SECONDS 3
static int sf;
static double ref(int ch, long n) {
	double t = (double)n / sf;
	return ch == 0 ? 0.40 * sin(2 * M_PI * 1000.0 * t) + 0.20 * sin(2 * M_PI * 15000.0 * t)
	               : 0.40 * sin(2 * M_PI * 440.0 * t) + 0.20 * sin(2 * M_PI * 9000.0 * t);
}

int main(int argc, char **argv) {
	if (argc != 4) return 2;
	sf = atoi(argv[1]);
	int eqmid = atoi(argv[2]);
	double want_db = atof(argv[3]);
	long total = (long)sf * SECONDS, n = 0, got = 0, bytes = 0, cap = (long)sf * (SECONDS + 1);
	int32_t in[LDACBT_ENC_LSU * 2], out[LDACBT_MAX_LSU * 2];
	int32_t *pcm = calloc(cap * 2, sizeof(int32_t));
	unsigned char pkt[2048];
	int errors = 0;

	HANDLE_LDAC_BT enc = ldacBT_get_handle(), dec = ldacBT_get_handle();
	if (ldacBT_init_handle_encode(enc, 679, eqmid, LDACBT_CHANNEL_MODE_STEREO, LDACBT_SMPL_FMT_S32, sf) != 0) {
		printf("FAIL: encoder init, error %d\n", ldacBT_get_error_code(enc)); return 1; }
	if (ldacBT_init_handle_decode(dec, LDACBT_CHANNEL_MODE_STEREO, sf, 0, 0, 0) == -1) {
		printf("FAIL: decoder init, error %d\n", ldacBT_get_error_code(dec)); return 1; }

	while (n < total) {
		for (int i = 0; i < LDACBT_ENC_LSU; i++, n++) {
			in[2 * i] = (int32_t)(2147483647.0 * ref(0, n));
			in[2 * i + 1] = (int32_t)(2147483647.0 * ref(1, n));
		}
		int used = 0, size = 0, frames = 0;
		if (ldacBT_encode(enc, in, &used, pkt, &size, &frames) != 0) {
			printf("FAIL: encode, error %d\n", ldacBT_get_error_code(enc)); return 1; }
		bytes += size;
		unsigned char *p = pkt;
		while (size > 0 && frames--) {
			int taken = 0, wrote = 0;
			if (ldacBT_decode(dec, p, (unsigned char *)out, LDACBT_SMPL_FMT_S32, size, &taken, &wrote) != 0) { errors++; break; }
			p += taken; size -= taken;
			for (int i = 0; i < wrote / 8 && got < cap; i++, got++) { pcm[2 * got] = out[2 * i]; pcm[2 * got + 1] = out[2 * i + 1]; }
		}
	}

	/* the codec delays the signal; find by how much, then measure over the middle second */
	long from = sf; double best = -1e9; int lag = 0;
	for (int l = 0; l < 1100; l++) {
		double c = 0;
		for (long k = from; k < from + 8192; k++)
			c += pcm[2 * (k + l)] / 2147483648.0 * ref(0, k) + pcm[2 * (k + l) + 1] / 2147483648.0 * ref(1, k);
		if (c > best) { best = c; lag = l; }
	}
	double worst = 1e9;
	for (int ch = 0; ch < 2; ch++) {
		double sig = 0, err = 0;
		for (long k = from; k < from + sf; k++) {
			double r = ref(ch, k), d = pcm[2 * (k + lag) + ch] / 2147483648.0;
			sig += r * r; err += (d - r) * (d - r);
		}
		double db = 10 * log10(sig / err);
		if (db < worst) worst = db;
	}
	int ok = errors == 0 && got > total - 4096 && worst >= want_db;
	printf("LDAC %6d Hz %4.0f kbps: %ld samples back, decode errors %d, signal-to-noise %.1f dB (need %.0f) %s\n",
	       sf, bytes * 8.0 / SECONDS / 1000, got, errors, worst, want_db, ok ? "PASS" : "FAIL");
	return !ok;
}
