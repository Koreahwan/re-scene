import React, { useEffect } from 'react';

interface ReviewModalPageProps {
  onClose: () => void;
  navigate?: (path: string) => void;
}

export const ReviewModalPage: React.FC<ReviewModalPageProps> = ({ onClose }) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div data-layer="영화 - 상세페이지 - 리뷰쓰기 (데이터가 있는 경우)" style={{ width: 1920, position: 'relative', background: 'var(--Gray-0, white)', display: 'flex', flexDirection: 'column' }}>
      {/* Top Hero Container (571px high, Y=90..661) */}
      <div style={{ width: 1920, height: 571, position: 'relative', overflow: 'hidden' }}>
        <div data-layer="Rectangle 240655225" style={{ width: 1920, height: 530.69, left: 0, top: 0, position: 'absolute', background: 'linear-gradient(180deg, #D9D9D9 0%, white 100%)' }} />
        <div data-layer="Backdrop Image" style={{ width: 120, height: 23, left: 943, top: 42, position: 'absolute', textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: '#4A4A4A', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>Backdrop Image</div>
        <div data-layer="Frame 2147227248" style={{ width: 1920, paddingLeft: 120, paddingRight: 120, left: 0, top: 156, position: 'absolute', justifyContent: 'flex-start', alignItems: 'flex-end', gap: 46, display: 'inline-flex' }}>
          <div data-layer="Frame 2147227244" style={{ width: 327, height: 415, paddingTop: 190, paddingBottom: 202, paddingLeft: 123, paddingRight: 123, background: '#838383', borderRadius: 20, flexDirection: 'column', justifyContent: 'center', alignItems: 'center', gap: 10, display: 'inline-flex' }}>
            <div data-layer="Film Poster" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'white', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>Film Poster</div>
          </div>
          <div data-layer="Frame 2147227247" style={{ flex: '1 1 0', justifyContent: 'space-between', alignItems: 'flex-start', display: 'flex' }}>
            <div data-layer="Frame 2147227246" style={{ width: 765, paddingBottom: 20, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 10, display: 'inline-flex' }}>
              <div data-layer="Frame 2147227243" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 40, display: 'flex' }}>
                <div data-layer="Frame 2147227230" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'flex' }}>
                  <div data-layer="Film Title" style={{ alignSelf: 'stretch', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'black', fontSize: 28, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '39.20px', wordWrap: 'break-word' }}>Film Title</div>
                  <div data-layer="Frame 2147227240" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'inline-flex' }}>
                    <div data-layer="Frame 2147227241" style={{ paddingRight: 12, borderRight: '1px var(--Gray-400, #AFAFB8) solid', justifyContent: 'center', alignItems: 'center', gap: 10, display: 'flex' }}>
                      <div data-layer="2025" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'black', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>2025</div>
                    </div>
                    <div data-layer="Frame 2147227242" style={{ paddingRight: 12, borderRight: '1px var(--Gray-400, #AFAFB8) solid', justifyContent: 'center', alignItems: 'center', gap: 10, display: 'flex' }}>
                      <div data-layer="156m" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'black', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>156m</div>
                    </div>
                    <div data-layer="PG-13" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'black', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>PG-13</div>
                  </div>
                </div>
                <div data-layer="Synopsis" style={{ alignSelf: 'stretch', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'black', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px', wordWrap: 'break-word' }}>Film synopsis and overview...</div>
              </div>
            </div>
            <div data-layer="AppButton" style={{ paddingLeft: 20, paddingRight: 20, paddingTop: 16, paddingBottom: 16, background: 'var(--Purple-500, #4C22F4)', borderRadius: 20, justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex' }}>
              <div data-layer="edit-02" style={{ width: 24, height: 24, position: 'relative', overflow: 'hidden' }}>
                <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M18 10.0003L14 6.0003M2.5 21.5003L5.88437 21.1243C6.29786 21.0783 6.5046 21.0553 6.69785 20.9928C6.86929 20.9373 7.03245 20.8589 7.18289 20.7597C7.35245 20.6479 7.49955 20.5008 7.79373 20.2066L21 7.0003C22.1046 5.89573 22.1046 4.10487 21 3.0003C19.8955 1.89573 18.1046 1.89573 17 3.0003L3.79373 16.2066C3.49955 16.5008 3.35246 16.6478 3.24064 16.8174C3.14143 16.9679 3.06301 17.131 3.00751 17.3025C2.94496 17.4957 2.92198 17.7024 2.87604 18.1159L2.5 21.5003Z" stroke="var(--Gray-0, white)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div data-layer="Write Review" style={{ textAlign: 'center', color: 'white', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '500', lineHeight: '26px', wordWrap: 'break-word' }}>Write Review</div>
            </div>
          </div>
        </div>
      </div>

      {/* Frame 2147227286 (Stats, Cast, Reviews, Reframe) */}
      <div data-layer="Frame 2147227286" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
        {/* Stats Row (180px high, Y=661..841) */}
        <div data-layer="Frame 2147227251" style={{ alignSelf: 'stretch', paddingTop: 60, paddingBottom: 40, paddingLeft: 120, paddingRight: 120, background: 'var(--Gray-0, white)', borderBottom: '1px var(--Gray-100, #F2F2F5) solid', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
          <div data-layer="Frame 2147227250" style={{ width: 140, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 16, display: 'inline-flex' }}>
            <div data-layer="Average Rating" style={{ alignSelf: 'stretch', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-700, #4A4A53)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>Average Rating</div>
            <div data-layer="Frame 2147227249" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'center', gap: 4, display: 'inline-flex' }}>
              <div data-layer="Star 3" style={{ width: 40, height: 40, background: '#FED200', borderRadius: 2.14 }}>
                <svg width="100%" height="100%" viewBox="0 0 34 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M14.639 1.19432C15.425 -0.398347 17.6961 -0.398347 18.4821 1.19432L21.9398 8.20038C22.252 8.83283 22.8553 9.27119 23.5533 9.37261L31.2849 10.4961C33.0425 10.7515 33.7443 12.9114 32.4725 14.1511L26.8778 19.6046C26.3728 20.0969 26.1423 20.8062 26.2616 21.5013L27.5823 29.2017C27.8825 30.9522 26.0452 32.2871 24.4731 31.4607L17.5577 27.825C16.9334 27.4968 16.1877 27.4968 15.5634 27.825L8.648 31.4607C7.07594 32.2871 5.23858 30.9522 5.53882 29.2017L6.85954 21.5013C6.97877 20.8062 6.7483 20.0969 6.24326 19.6046L0.648594 14.1511C-0.623228 12.9114 0.0785799 10.7515 1.83619 10.4961L9.56784 9.37261C10.2658 9.27119 10.8691 8.83283 11.1813 8.20038L14.639 1.19432Z" fill="#FED200" />
                </svg>
              </div>
              <div data-layer="4.1" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'black', fontSize: 28, fontFamily: 'Pretendard', fontWeight: '700', wordWrap: 'break-word' }}>4.1</div>
            </div>
          </div>
          <div data-layer="Frame 2147227252" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 16, display: 'flex' }}>
            <div data-layer="🍅 50%" style={{ textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>🍅 50%</div>
            <div data-layer="🍿 50%" style={{ textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>🍿 50%</div>
            <div data-layer="IMDb: 50%" style={{ textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>IMDb: 50%</div>
          </div>
        </div>

        {/* Cast Section (349px high, Y=841..1190) */}
        <div data-layer="Frame 2147227275" style={{ alignSelf: 'stretch', paddingLeft: 120, paddingRight: 120, paddingTop: 40, paddingBottom: 40, background: 'var(--Gray-50, #F8F8FA)', borderBottom: '1px var(--Gray-100, #F2F2F5) solid', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'flex' }}>
          <div data-layer="Director / Cast" style={{ alignSelf: 'stretch', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-700, #4A4A53)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>Director / Cast</div>
          <div data-layer="Frame 2147227256" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'center', gap: 16, display: 'inline-flex' }}>
            {[1, 2, 3, 4, 5, 6, 7].map((idx) => (
              <div key={idx} data-layer={`Frame 214722726${idx}`} style={{ flex: '1 1 0', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 10, display: 'inline-flex' }}>
                <div data-layer="Rectangle 240655229" style={{ alignSelf: 'stretch', height: 190, background: '#D9D9D9', borderRadius: 20 }} />
                <div data-layer="Name" style={{ alignSelf: 'stretch', textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-700, #4A4A53)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>Cast {idx}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Critic Reviews Section (381px high, Y=1190..1571) */}
        <div data-layer="Frame 2147227283" style={{ alignSelf: 'stretch', paddingLeft: 120, paddingRight: 120, paddingTop: 40, paddingBottom: 40, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'flex' }}>
          <div data-layer="Frame 2147227205" style={{ alignSelf: 'stretch', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
            <div data-layer="Critic Reviews" style={{ flex: '1 1 0', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-700, #4A4A53)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>Critic Reviews</div>
          </div>
          <div data-layer="Frame 2147227282" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'center', gap: 20, display: 'inline-flex' }}>
            {[1, 2].map((i) => (
              <div key={i} data-layer={`Frame 214722728${i - 1}`} style={{ flex: '1 1 0', height: 253, overflow: 'hidden', paddingTop: 40, paddingBottom: 40, paddingLeft: 40, paddingRight: 244, background: 'var(--Gray-50, #F8F8FA)', borderRadius: 20, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 10, display: 'inline-flex' }}>
                <div data-layer="Frame 2147227277" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 36, display: 'inline-flex' }}>
                  <div data-layer="Ellipse 1" style={{ width: 70, height: 70, background: '#D9D9D9', borderRadius: 9999 }} />
                  <div data-layer="Frame 2147227276" style={{ width: 226.29, paddingTop: 12, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'inline-flex' }}>
                    <div data-layer="Frame 2147227207" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 8, display: 'inline-flex' }}>
                      <div data-layer="Frame 2147227208">
                        <svg width="120" height="24" viewBox="0 0 120 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                          {[0, 24, 48, 72].map((off) => (
                            <path key={off} d={`M${10.8471 + off} 2.33613C${11.3187 + off} 1.38052 ${12.6813 + off} 1.38052 ${13.1529 + off} 2.33612L${15.2276 + off} 6.53976C${15.4148 + off} 6.91923 ${15.7769 + off} 7.18225 ${16.1956 + off} 7.2431L${20.8346 + off} 7.91718C${21.8892 + off} 8.07042 ${22.3103 + off} 9.36638 ${21.5472 + off} 10.1102L${18.1904 + off} 13.3823C${17.8873 + off} 13.6777 ${17.7491 + off} 14.1032 ${17.8206 + off} 14.5203L${18.613 + off} 19.1406C${18.7932 + off} 20.1909 ${17.6908 + off} 20.9918 ${16.7475 + off} 20.4959L${12.5983 + off} 18.3145C${12.2237 + off} 18.1176 ${11.7763 + off} 18.1176 ${11.4017 + off} 18.3145L${7.25247 + off} 20.4959C${6.30924 + off} 20.9918 ${5.20682 + off} 20.1909 ${5.38696 + off} 19.1406L${6.1794 + off} 14.5203C${6.25093 + off} 14.1032 ${6.11265 + off} 13.6777 ${5.80963 + off} 13.3823L${2.45283 + off} 10.1102C${1.68974 + off} 9.36638 ${2.11082 + off} 8.07042 ${3.16539 + off} 7.91718L${7.80437 + off} 7.2431C${8.22314 + off} 7.18225 ${8.58516 + off} 6.91923 ${8.77244 + off} 6.53976L${10.8471 + off} 2.33613Z`} fill="#FED200" />
                          ))}
                          <path d="M106.847 2.33613C107.319 1.38052 108.681 1.38052 109.153 2.33612L111.228 6.53976C111.415 6.91923 111.777 7.18225 112.196 7.2431L116.835 7.91718C117.889 8.07042 118.31 9.36638 117.547 10.1102L114.19 13.3823C113.887 13.6777 113.749 14.1032 113.821 14.5203L114.613 19.1406C114.793 20.1909 113.691 20.9918 112.748 20.4959L108.598 18.3145C108.224 18.1176 107.776 18.1176 107.402 18.3145L103.252 20.4959C102.309 20.9918 101.207 20.1909 101.387 19.1406L102.179 14.5203C102.251 14.1032 102.113 13.6777 101.81 13.3823L98.4528 10.1102C97.6897 9.36638 98.1108 8.07042 99.1654 7.91718L103.804 7.2431C104.223 7.18225 104.585 6.91923 104.772 6.53976L106.847 2.33613Z" fill="var(--Gray-200, #E6E6EA)" />
                        </svg>
                      </div>
                      <div data-layer="4" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-400, #AFAFB8)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>4</div>
                    </div>
                    <div data-layer="Frame 2147227279" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'flex' }}>
                      <div data-layer="Frame 2147227278" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'center', gap: 16, display: 'inline-flex' }}>
                        <div data-layer="Reviewer Name" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-700, #4A4A53)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>Reviewer Name</div>
                        <div data-layer="2025.06" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '300', wordWrap: 'break-word' }}>2025.06</div>
                      </div>
                      <div data-layer="Critic review content..." style={{ alignSelf: 'stretch', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px', wordWrap: 'break-word' }}>Insightful commentary on the film's narrative structure and technical execution.</div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Reframe Section (757px high, Y=1571..2328) */}
        <div data-layer="Frame 2147227196" style={{ alignSelf: 'stretch', paddingLeft: 120, paddingRight: 120, paddingTop: 50, paddingBottom: 50, background: 'var(--Gray-50, #F8F8FA)', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 16, display: 'flex' }}>
          <div data-layer="Frame 2147227313" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'flex' }}>
            <div data-layer="Frame 2147227205" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'center', gap: 12, display: 'inline-flex' }}>
              <div data-layer="Reframe" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-700, #4A4A53)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>Reframe</div>
              <div data-layer="Total Runtime 00:00:00" style={{ flex: '1 1 0', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>Total Runtime 00:00:00</div>
            </div>
            <div data-layer="Frame 2147227312" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
              <div data-layer="Frame 2147227308" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'inline-flex' }}>
                <div data-layer="Rectangle 240655233" style={{ width: 512, height: 8, background: 'var(--Purple-500, #4C22F4)' }} />
                <div data-layer="Rectangle 240655234" style={{ flex: '1 1 0', height: 8, background: 'var(--Gray-200, #E6E6EA)' }} />
              </div>
              <div data-layer="Frame 2147227311" style={{ alignSelf: 'stretch', paddingLeft: 16, paddingRight: 16, justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11].map((n) => (
                  <div key={n} data-layer="00:00:00" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: n === 4 ? 'var(--Purple-500, #4C22F4)' : 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '300', wordWrap: 'break-word' }}>00:00:00</div>
                ))}
              </div>
            </div>
          </div>
          <div data-layer="Frame 2147227190" style={{ alignSelf: 'stretch', height: 532, position: 'relative' }}>
            {[
              { id: '1', left: 0, top: 0, layer: 'Frame 2147227187' },
              { id: '2', left: 850, top: 0, layer: 'Frame 2147227307' },
              { id: '3', left: 0, top: 276, layer: 'Frame 2147227308' },
              { id: '4', left: 850, top: 276, layer: 'Frame 2147227309' },
            ].map((card) => (
              <div
                key={card.id}
                data-layer={card.layer}
                style={{ width: 830, paddingLeft: 30, paddingRight: 30, paddingTop: 32, paddingBottom: 32, background: 'var(--Gray-0, white)', borderRadius: 12, left: card.left, top: card.top, position: 'absolute', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 10, display: 'inline-flex' }}
              >
                <div data-layer="Frame 2147227177" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
                  <div data-layer="Frame 2147227297" style={{ alignSelf: 'stretch', justifyContent: 'space-between', alignItems: 'center', display: 'inline-flex' }}>
                    <div data-layer="Frame 2147227302" style={{ width: 586.75, justifyContent: 'flex-start', alignItems: 'center', gap: 8, display: 'flex' }}>
                      <div data-layer="SCENE 1" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Purple-500, #4C22F4)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>SCENE 1</div>
                      <div data-layer="Frame 2147227309" style={{ padding: 4, background: 'var(--Purple-50, #F1F0FF)', borderRadius: 4, justifyContent: 'center', alignItems: 'center', gap: 10, display: 'flex' }}>
                        <div data-layer="[00:00:00]" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Purple-300, #B7B3FF)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>[00:00:00]</div>
                      </div>
                    </div>
                    <div onClick={onClose} data-layer="Frame 2147227206" style={{ justifyContent: 'flex-end', alignItems: 'center', gap: 4, display: 'flex', cursor: 'pointer' }}>
                      <div data-layer="More" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>More</div>
                      <div data-layer="chevron-right" style={{ width: 20, height: 20, position: 'relative', overflow: 'hidden' }}>
                        <svg width="100%" height="100%" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <path d="M7.5 15L12.5 10L7.5 5" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.66667" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                    </div>
                  </div>
                  <div data-layer="Frame 2147227305" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 28, display: 'flex' }}>
                    <div data-layer="Frame 2147227185" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'center', alignItems: 'flex-start', gap: 32, display: 'flex' }}>
                      <div data-layer="Frame 2147227177" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
                        <div data-layer="Frame 2147227186" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 15, display: 'flex' }}>
                          <div data-layer="Frame 2147227209" style={{ flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
                            <div data-layer="Key Scene Summary" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>Key Scene Summary</div>
                          </div>
                          <div data-layer="Frame 2147227210" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
                            <div style={{ alignSelf: 'stretch', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px', wordWrap: 'break-word' }}>Detailed interpretation connecting the scene to forensic clues and narrative reveals.</div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div data-layer="Frame 2147227304" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'inline-flex' }}>
                      <div data-layer="LikeButton" style={{ padding: 6, borderRadius: 8, justifyContent: 'center', alignItems: 'center', gap: 6, display: 'flex' }}>
                        <div data-layer="Icon" style={{ width: 20, height: 20, position: 'relative' }}>
                          <svg width="100%" height="100%" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M10.293 17.4268C10.1097 17.5241 9.89032 17.5241 9.70703 17.4268L10 16.875L10.293 17.4268ZM16.875 6.875C16.875 5.17291 15.4302 3.75 13.5938 3.75C12.2253 3.75 11.0661 4.54535 10.5713 5.65674C10.4709 5.88228 10.2469 6.02783 10 6.02783C9.75312 6.02783 9.52909 5.88228 9.42871 5.65674C8.93392 4.54535 7.77467 3.75 6.40625 3.75C4.56977 3.75 3.125 5.17291 3.125 6.875C3.125 9.62122 4.84375 11.9659 6.67643 13.6743C7.58245 14.5189 8.49097 15.184 9.17399 15.638C9.5147 15.8645 9.79788 16.0376 9.9943 16.1532C9.99607 16.1542 9.99825 16.1554 10 16.1564C10.0017 16.1554 10.0039 16.1542 10.0057 16.1532C10.2021 16.0376 10.4853 15.8645 10.826 15.638C11.509 15.184 12.4175 14.5189 13.3236 13.6743C15.1562 11.9659 16.875 9.62122 16.875 6.875ZM18.125 6.875C18.125 10.1457 16.0937 12.8009 14.1764 14.5882C13.2076 15.4914 12.2409 16.1981 11.5177 16.6789C11.1556 16.9196 10.8526 17.1049 10.6388 17.2306C10.5322 17.2934 10.4478 17.3419 10.389 17.3747C10.3596 17.3911 10.3359 17.4034 10.3198 17.4121C10.3119 17.4164 10.3056 17.4203 10.3011 17.4227C10.299 17.4238 10.2975 17.4252 10.2962 17.4259L10.2938 17.4268L10 16.875L9.70622 17.4268L9.70378 17.4259C9.70246 17.4252 9.70101 17.4238 9.69889 17.4227C9.6944 17.4203 9.68815 17.4164 9.68018 17.4121C9.6641 17.4034 9.64045 17.3911 9.611 17.3747C9.55217 17.3419 9.46783 17.2934 9.36117 17.2306C9.14745 17.1049 8.84445 16.9196 8.48226 16.6789C7.75909 16.1981 6.7924 15.4914 5.82357 14.5882C3.90634 12.8009 1.875 10.1457 1.875 6.875C1.875 4.43495 3.928 2.5 6.40625 2.5C7.86485 2.5 9.16869 3.16863 10 4.21387C10.8313 3.16863 12.1352 2.5 13.5938 2.5C16.072 2.5 18.125 4.43495 18.125 6.875Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </div>
                        <div data-layer="Like Count" style={{ color: 'var(--Gray-400, #AFAFB8)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>293</div>
                      </div>
                      <div data-layer="CountItem" style={{ padding: 6, borderRadius: 8, justifyContent: 'center', alignItems: 'center', gap: 6, display: 'flex' }}>
                        <div data-layer="Icon" style={{ width: 20, height: 20, position: 'relative' }}>
                          <svg width="100%" height="100%" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M7.1875 9.6875C7.1875 9.86009 7.04759 10 6.875 10C6.70241 10 6.5625 9.86009 6.5625 9.6875C6.5625 9.51491 6.70241 9.375 6.875 9.375C7.04759 9.375 7.1875 9.51491 7.1875 9.6875ZM7.1875 9.6875H6.875M10.3125 9.6875C10.3125 9.86009 10.1726 10 10 10C9.82741 10 9.6875 9.86009 9.6875 9.6875C9.6875 9.51491 9.82741 9.375 10 9.375C10.1726 9.375 10.3125 9.51491 10.3125 9.6875ZM10.3125 9.6875H10M13.4375 9.6875C13.4375 9.86009 13.2976 10 13.125 10C12.9524 10 12.8125 9.86009 12.8125 9.6875C12.8125 9.51491 12.9524 9.375 13.125 9.375C13.2976 9.375 13.4375 9.51491 13.4375 9.6875ZM13.4375 9.6875H13.125M17.5 9.6875C17.5 13.4845 14.1421 16.5625 10 16.5625C9.26044 16.5625 8.54588 16.4644 7.87098 16.2816C7.05847 16.8524 6.06834 17.1875 5 17.1875C4.83398 17.1875 4.6698 17.1794 4.50806 17.1636C4.375 17.1506 4.24316 17.1324 4.11316 17.1091C4.5161 16.6336 4.80231 16.0564 4.92824 15.4215C5.00378 15.0406 4.81725 14.6707 4.53903 14.3999C3.27475 13.1693 2.5 11.5113 2.5 9.6875C2.5 5.89054 5.85786 2.8125 10 2.8125C14.1421 2.8125 17.5 5.89054 17.5 9.6875Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </div>
                        <div data-layer="Like Count" style={{ color: 'var(--Gray-400, #AFAFB8)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>16</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Frame 5 Modal Overlay & Content */}
      <div data-layer="Rectangle 240655231" style={{ width: 1920, height: 2546, left: 0, top: -90, position: 'absolute', background: 'rgba(0, 0, 0, 0.40)', zIndex: 1000 }} />
      <div data-layer="AppModal" style={{ width: 795, paddingTop: 32, paddingBottom: 24, paddingLeft: 24, paddingRight: 24, left: 563, top: 190, position: 'absolute', background: 'white', boxShadow: '0px 0px 20px rgba(30, 41, 59, 0.10)', borderRadius: 12, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'inline-flex', zIndex: 1001 }}>
        <div data-layer="Container" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'flex' }}>
          <div data-layer="Frame 1010106602" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'center', gap: 8, display: 'flex' }}>
            <div data-layer="Container" style={{ alignSelf: 'stretch', justifyContent: 'center', alignItems: 'flex-start', gap: 16, display: 'inline-flex' }}>
              <div data-layer="Container" style={{ flex: '1 1 0', justifyContent: 'center', alignItems: 'center', gap: 6, display: 'flex', flexWrap: 'wrap', alignContent: 'center' }}>
                <div data-layer="Frame 1010106608" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 6, display: 'flex' }}>
                  <div data-layer="Title" style={{ textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 24, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>Write Review</div>
                </div>
              </div>
              <div onClick={onClose} data-layer="CustomButton" style={{ width: 24, height: 24, position: 'relative', background: 'rgba(255, 255, 255, 0)', borderRadius: 4, cursor: 'pointer' }}>
                <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M6 17.999L18 5.99902M6 5.99902L18 17.999" stroke="var(--Semantic-Action-Foreground-Grayblue-Light-Default, #A0AEC0)" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </div>
            <div data-layer="Subtitle" style={{ alignSelf: 'stretch', textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>Leave a review for this film!</div>
          </div>
          <div data-layer="Slot" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 32, display: 'flex' }}>
            <div data-layer="Frame 608228" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 32, display: 'flex' }}>
              <div data-layer="Frame 2147227299" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'center', gap: 12, display: 'flex' }}>
                <div data-layer="Frame 607541" style={{ alignSelf: 'stretch', justifyContent: 'center', alignItems: 'flex-start', gap: 12, display: 'inline-flex' }}>
                  <div data-layer="Frame 2147227208">
                    <svg width="210" height="42" viewBox="0 0 210 42" fill="none" xmlns="http://www.w3.org/2000/svg">
                      {[0, 42, 84, 126].map((off) => (
                        <path key={off} d={`M${18.9823 + off} 4.08822C${19.8077 + off} 2.41592 ${22.1923 + off} 2.41592 ${23.0177 + off} 4.08822L${26.6482 + off} 11.4446C${26.976 + off} 12.1087 ${27.6095 + off} 12.5689 ${28.3423 + off} 12.6754L${36.4606 + off} 13.8551C${38.3061 + off} 14.1232 ${39.043 + off} 16.3912 ${37.7076 + off} 17.6929L${31.8331 + off} 23.419C${31.3029 + off} 23.9359 ${31.0609 + off} 24.6807 ${31.1861 + off} 25.4105L${32.5728 + off} 33.496C${32.8881 + off} 35.334 ${30.9588 + off} 36.7357 ${29.3082 + off} 35.8679L${22.047 + off} 32.0504C${21.3915 + off} 31.7058 ${20.6085 + off} 31.7058 ${19.953 + off} 32.0504L${12.6918 + off} 35.8679C${11.0412 + off} 36.7357 ${9.11194 + off} 35.334 ${9.42719 + off} 33.496L${10.8139 + off} 25.4105C${10.9391 + off} 24.6807 ${10.6971 + off} 23.9359 ${10.1669 + off} 23.419L${4.29245 + off} 17.6929C${2.95704 + off} 16.3912 ${3.69393 + off} 14.1232 ${5.53943 + off} 13.8551L${13.6577 + off} 12.6754C${14.3905 + off} 12.5689 ${15.024 + off} 12.1087 ${15.3518 + off} 11.4446L${18.9823 + off} 4.08822Z`} fill="#FED200" />
                      ))}
                      <path d="M186.982 4.08822C187.808 2.41592 190.192 2.41592 191.018 4.08822L194.648 11.4446C194.976 12.1087 195.609 12.5689 196.342 12.6754L204.461 13.8551C206.306 14.1232 207.043 16.3912 205.708 17.6929L199.833 23.419C199.303 23.9359 199.061 24.6807 199.186 25.4105L200.573 33.496C200.888 35.334 198.959 36.7357 197.308 35.8679L190.047 32.0504C189.392 31.7058 188.608 31.7058 187.953 32.0504L180.692 35.8679C179.041 36.7357 177.112 35.334 177.427 33.496L178.814 25.4105C178.939 24.6807 178.697 23.9359 178.167 23.419L172.292 17.6929C170.957 16.3912 171.694 14.1232 173.539 13.8551L181.658 12.6754C182.391 12.5689 183.024 12.1087 183.352 11.4446L186.982 4.08822Z" fill="var(--Gray-100, #F2F2F5)" />
                    </svg>
                  </div>
                </div>
              </div>
              <div data-layer="profile-discover" style={{ alignSelf: 'stretch', height: 178, padding: 20, borderRadius: 12, outline: '1px var(--Gray-200, #E6E6EA) solid', outlineOffset: '-1px', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 16, display: 'flex' }}>
                <div data-layer="Placeholder" style={{ color: 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>Write your review here...</div>
              </div>
            </div>
            <div data-layer="Frame 606878" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'inline-flex' }}>
              <div onClick={onClose} data-layer="AppButton" style={{ flex: '1 1 0', paddingLeft: 20, paddingRight: 20, paddingTop: 16, paddingBottom: 16, background: 'var(--Gray-200, #E6E6EA)', borderRadius: 20, justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex', cursor: 'pointer' }}>
                <div data-layer="Cancel" style={{ textAlign: 'center', color: 'var(--Gray-600, #6B6B75)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '500', lineHeight: '26px', wordWrap: 'break-word' }}>Cancel</div>
              </div>
              <div onClick={onClose} data-layer="AppButton" style={{ flex: '1 1 0', paddingLeft: 20, paddingRight: 20, paddingTop: 16, paddingBottom: 16, background: 'var(--Purple-500, #4C22F4)', borderRadius: 20, justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex', cursor: 'pointer' }}>
                <div data-layer="Save" style={{ textAlign: 'center', color: 'white', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '500', lineHeight: '26px', wordWrap: 'break-word' }}>Save</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Frame 5 AppToast */}
      <div data-layer="AppToast" style={{ height: 40, maxWidth: 500, padding: 12, left: 1634, top: 30, position: 'absolute', background: 'var(--Purple-50, #F1F0FF)', boxShadow: '0px 0px 12px rgba(30, 41, 59, 0.10)', borderRadius: 8, outline: '1px var(--Purple-500, #4C22F4) solid', outlineOffset: '-1px', justifyContent: 'flex-start', alignItems: 'center', gap: 16, display: 'inline-flex', zIndex: 1002 }}>
        <div data-layer="Frame 607914" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 8, display: 'flex' }}>
          <div data-layer="Icon" style={{ width: 20, height: 20, position: 'relative' }}>
            <svg width="100%" height="100%" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path fillRule="evenodd" clipRule="evenodd" d="M10 18C14.4183 18 18 14.4183 18 10C18 5.58172 14.4183 2 10 2C5.58172 2 2 5.58172 2 10C2 14.4183 5.58172 18 10 18ZM13.8566 8.19113C14.1002 7.85614 14.0261 7.38708 13.6911 7.14345C13.3561 6.89982 12.8871 6.97388 12.6434 7.30887L9.15969 12.099L7.28033 10.2197C6.98744 9.92678 6.51256 9.92678 6.21967 10.2197C5.92678 10.5126 5.92678 10.9874 6.21967 11.2803L8.71967 13.7803C8.87477 13.9354 9.08999 14.0149 9.30867 13.9977C9.52734 13.9805 9.72754 13.8685 9.85655 13.6911L13.8566 8.19113Z" fill="var(--Purple-400, #8277FF)" />
            </svg>
          </div>
          <div data-layer="Description" style={{ color: 'var(--Gray-700, #4A4A53)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>Review submitted successfully</div>
        </div>
        <div onClick={onClose} data-layer="CustomButton" style={{ width: 18, height: 18, position: 'relative', background: 'rgba(255, 255, 255, 0)', borderRadius: 4, cursor: 'pointer' }}>
          <svg width="100%" height="100%" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M4.5 13.5L13.5 4.5M4.5 4.5L13.5 13.5" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>
    </div>
  );
};
