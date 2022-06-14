#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center

ONE_KIB = 1024
ONE_MIB = 1024 * ONE_KIB
GCS_CHUNK_SIZE = 256 * ONE_KIB
UPLOAD_BUFFER_SIZE = 64 * GCS_CHUNK_SIZE
MAX_SINGLE_PART_SIZE = 128 * ONE_MIB
COMPOSE_MAX_PARTS = 32
