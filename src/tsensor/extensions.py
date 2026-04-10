from tsensor.core.data_stream import DataStream


TOTAL_SAMPLES = 1_000_000
TOTA_TEMPORAL_SAMPLES = 1_000
data_stream = DataStream(total_samples=TOTAL_SAMPLES)
buffer_stream = DataStream(total_samples=TOTA_TEMPORAL_SAMPLES)
history_stream = DataStream(total_samples=TOTA_TEMPORAL_SAMPLES)
