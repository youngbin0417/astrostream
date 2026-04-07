import time
from astrostream import AutoParser
from tests.dummy_stream import run_dummy_generator

def on_position(pos):
    """
    콜백 함수: GPS 위치 데이터가 성공적으로 파싱될 때마다 호출됩니다.
    """
    print(f"[AstroStream] 위치 수신됨 - 위도: {pos.lat:.6f}, 경도: {pos.lon:.6f} | 고도: {pos.alt:.2f}m | 위성 수: {pos.num_sats} | Fix 유형: {pos.fix_type}")

def main():
    print("🚀 AstroStream 라이브러리 구동 테스트를 시작합니다...")
    print(" - 랜덤한 NMEA 및 UBX (바이너리) 데이터를 파서에 주입합니다.")
    print(" - 'Ctrl+C'를 눌러 종료하세요.\n")
    
    # 1. 파서 객체 생성 (데이터가 파싱되면 on_position 콜백 실행)
    parser = AutoParser(callback=on_position)
    
    try:
        # 2. 테스트용 더미 데이터 스트림 생성기를 돌려서 파서에 데이터를 주입(feed)합니다.
        # 실제 환경에서는 시리얼 통신(serial.read())으로 받은 데이터를 parser.feed()에 넘겨주시면 됩니다.
        run_dummy_generator(parser.feed)
    except KeyboardInterrupt:
        print("\n테스트가 종료되었습니다.")

if __name__ == "__main__":
    main()
