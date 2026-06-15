from slowapi import Limiter
from slowapi.util import get_remote_address

# slowapi가 .env를 시스템 인코딩(cp949)으로 읽으면 한글 주석에서 UnicodeDecodeError 발생.
# 존재하지 않는 파일명을 넘겨 파일 읽기를 건너뛰고, os.environ 에서만 설정값을 읽도록 한다.
limiter = Limiter(key_func=get_remote_address, config_filename="__no_env_file__")
