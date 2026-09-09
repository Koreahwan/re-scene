import React, { useState, useEffect } from 'react';

interface ProfilePageProps {
  navigate?: (path: string) => void;
}

export const ProfilePage: React.FC<ProfilePageProps> = ({ navigate }) => {
  const getInitialTab = (): 'reviews' | 'posts' | 'comments' | 'likes' => {
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      const tabParam = urlParams.get('tab');
      if (tabParam === 'likes') return 'likes';
      if (tabParam === 'posts') return 'posts';
      if (tabParam === 'comments') return 'comments';
    }
    return 'reviews';
  };

  const [activeTab, setActiveTab] = useState<'reviews' | 'posts' | 'comments' | 'likes'>(getInitialTab);

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const tabParam = urlParams.get('tab');
    if (tabParam === 'likes') {
      setActiveTab('likes');
    } else if (tabParam === 'posts') {
      setActiveTab('posts');
    } else if (tabParam === 'comments') {
      setActiveTab('comments');
    } else {
      setActiveTab('reviews');
    }
  }, []);

  const likeImages = [
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I88-14627-73-6941.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I88-14628-73-6941.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I88-14629-73-6941.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I88-14630-73-6941.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I88-14631-73-6941.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I88-14632-73-6941.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I88-14633-73-6941.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I88-14634-73-6941.png',
  ];

  const reviewImages = [
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-88-14716.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-88-14744.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-88-14767.png',
    '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-88-14786.png',
  ];

  return (
    <div data-layer={activeTab === 'likes' ? '마이페이지 - 좋아요' : '마이페이지 - 리뷰'} style={{ width: 1920, position: 'relative', background: 'var(--Gray-0, white)', flexDirection: 'column', display: 'flex' }}>
      <div data-layer="Frame 2147227287" style={{ alignSelf: 'stretch', paddingLeft: 120, paddingRight: 120, paddingTop: 20, paddingBottom: 20, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'flex' }}>
        <div data-layer="Frame 2147227339" style={{ flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'flex' }}>
          <div data-layer="마이페이지" style={{ color: 'var(--Gray-800, #2D2D34)', fontSize: 28, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>
            마이페이지
          </div>
        </div>

        {/* User Profile Card (1:1 Figma Frame 2147227330) */}
        <div data-layer="Frame 2147227337" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'flex' }}>
          <div data-layer="Frame 2147227330" style={{ alignSelf: 'stretch', height: 222, boxSizing: 'border-box', paddingLeft: 32, paddingRight: 32, paddingTop: 40, paddingBottom: 40, background: 'var(--Gray-50, #F8F8FA)', borderRadius: 16, justifyContent: 'flex-start', alignItems: 'flex-start', gap: 10, display: 'inline-flex' }}>
            <div data-layer="Frame 2147227329" style={{ flex: '1 1 0', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 28, display: 'flex' }}>
              <div data-layer="Ellipse 2" style={{ width: 100, height: 100, background: '#D9D9D9', borderRadius: 9999 }} />
              <div data-layer="Frame 2147227327" style={{ flex: '1 1 0', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'center', gap: 28, display: 'inline-flex' }}>
                <div data-layer="Frame 2147227336" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'flex' }}>
                  <div data-layer="Frame 2147227331" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Gray-700, #4A4A53)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>
                      사용자
                    </div>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>
                      사용자가 직접 적는 한줄 소개
                    </div>
                  </div>
                  <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Gray-400, #AFAFB8)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>
                    RE: SCENE@gmail.com
                  </div>
                </div>
                <div data-layer="Frame 2147227334" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 40, display: 'inline-flex' }}>
                  <div data-layer="Frame 2147227332" style={{ flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 4, display: 'inline-flex' }}>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>리뷰</div>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Purple-500, #4C22F4)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>100</div>
                  </div>
                  <div data-layer="Frame 2147227333" style={{ flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 4, display: 'inline-flex' }}>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>게시글</div>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Purple-500, #4C22F4)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>100</div>
                  </div>
                  <div data-layer="Frame 2147227336" style={{ flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 4, display: 'inline-flex' }}>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>댓글</div>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Purple-500, #4C22F4)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>100</div>
                  </div>
                  <div data-layer="Frame 2147227334" style={{ flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 4, display: 'inline-flex' }}>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>좋아요</div>
                    <div data-layer="Text" style={{ alignSelf: 'stretch', color: 'var(--Purple-500, #4C22F4)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>100</div>
                  </div>
                </div>
              </div>
              <div data-layer="AppButton" style={{ paddingLeft: 20, paddingRight: 20, paddingTop: 12, paddingBottom: 12, background: 'var(--Gray-200, #E6E6EA)', borderRadius: 20, justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex', cursor: 'pointer' }}>
                <div data-layer="저장하기" style={{ textAlign: 'center', color: 'var(--Gray-600, #6B6B75)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500', lineHeight: '24px', wordWrap: 'break-word' }}>
                  수정하기
                </div>
              </div>
            </div>
          </div>

          {/* 4 Tabs (1:1 Figma) */}
          <div data-layer="Frame 2147227342" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'flex' }}>
            <div data-layer="TabList" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'center', display: 'inline-flex' }}>
              <div
                onClick={() => setActiveTab('reviews')}
                data-layer="AppLineTab/TabItem"
                style={{ flex: '1 1 0', height: 44, maxWidth: 200, paddingLeft: 16, paddingRight: 16, borderBottom: activeTab === 'reviews' ? '2px var(--Gray-800, #2D2D34) solid' : 'none', justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex', cursor: 'pointer' }}
              >
                <div data-layer="Description" style={{ flex: '1 1 0', textAlign: 'center', color: activeTab === 'reviews' ? 'var(--Gray-800, #2D2D34)' : (activeTab === 'likes' ? 'var(--Global-Text-Caption, #8C9BB0)' : 'var(--Gray-400, #AFAFB8)'), fontSize: 16, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>
                  나의 리뷰
                </div>
              </div>
              <div
                onClick={() => setActiveTab('posts')}
                data-layer="AppLineTab/TabItem"
                style={{ flex: '1 1 0', height: 44, maxWidth: 200, paddingLeft: 16, paddingRight: 16, borderBottom: activeTab === 'posts' ? '2px var(--Global-Line-Strong, #1E293B) solid' : 'none', justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex', cursor: 'pointer' }}
              >
                <div data-layer="Description" style={{ flex: '1 1 0', textAlign: 'center', color: activeTab === 'posts' ? 'var(--Global-Text-Strong, #1E293B)' : 'var(--Gray-400, #AFAFB8)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>
                  내가 쓴 글
                </div>
              </div>
              <div
                onClick={() => setActiveTab('comments')}
                data-layer="AppLineTab/TabItem"
                style={{ flex: '1 1 0', height: 44, maxWidth: 200, paddingLeft: 16, paddingRight: 16, borderBottom: activeTab === 'comments' ? '2px var(--Global-Line-Strong, #1E293B) solid' : 'none', justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex', cursor: 'pointer' }}
              >
                <div data-layer="Description" style={{ flex: '1 1 0', textAlign: 'center', color: activeTab === 'comments' ? 'var(--Global-Text-Strong, #1E293B)' : 'var(--Gray-400, #AFAFB8)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>
                  댓글 단 글
                </div>
              </div>
              <div
                onClick={() => setActiveTab('likes')}
                data-layer="AppLineTab/TabItem"
                style={{ flex: '1 1 0', height: 44, maxWidth: 200, paddingLeft: 16, paddingRight: 16, borderBottom: activeTab === 'likes' ? '2px var(--Global-Line-Strong, #1E293B) solid' : 'none', justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex', cursor: 'pointer' }}
              >
                <div data-layer="Description" style={{ flex: '1 1 0', textAlign: 'center', color: activeTab === 'likes' ? 'var(--Global-Text-Strong, #1E293B)' : 'var(--Gray-400, #AFAFB8)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>
                  찜한 영화
                </div>
              </div>
            </div>

            {/* Tab 1: 나의 리뷰 (1:1 Figma Frame 11) */}
            {activeTab === 'reviews' && (
              <>
                <div data-layer="Frame 2147227344" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'inline-flex' }}>
                  {[0, 1].map((idx) => (
                    <div
                      key={idx}
                      onClick={() => navigate?.('/films/the-bat-whispers-1930')}
                      data-layer={idx === 0 ? 'Frame 2147227280' : 'Frame 2147227281'}
                      style={{ width: 830, height: 279, padding: 40, background: 'var(--Gray-50, #F8F8FA)', borderRadius: 20, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 10, display: 'inline-flex', cursor: 'pointer' }}
                    >
                      <div data-layer="Frame 2147227277" style={{ alignSelf: 'stretch', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
                        <div data-layer="Frame 2147227343" style={{ width: 549, justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'flex' }}>
                          <img
                            data-layer="UCH80I8j8DZbiADBlXGQ66se2GecV-OTj-bQoQSuWbU-2ypYVRr2B43aDCiRFGJxxqIGwjnyHRc3Ngh3s5miXQ 1"
                            style={{ width: 159, height: 199, borderRadius: 12, objectFit: 'cover' }}
                            src={reviewImages[idx]}
                            alt="Movie Poster"
                            onError={(e) => { (e.target as HTMLImageElement).src = '/assets/poster_the_bat_whispers-Dg94dkRz.jpg'; }}
                          />
                          <div data-layer="Frame 2147227276" style={{ height: 178, paddingTop: 12, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'inline-flex' }}>
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
                            <div data-layer="Frame 2147227279" style={{ alignSelf: 'stretch', flex: '1 1 0', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'flex' }}>
                              <div data-layer="Frame 2147227278" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'center', gap: 16, display: 'inline-flex' }}>
                                <div data-layer="간단한 제목" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-700, #4A4A53)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>간단한 제목</div>
                              </div>
                              <div data-layer="해당 리뷰를 그렇게 작성한 이유를 보다 자세히 적어주세요. 최대 4줄로 구성가능합니다." style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px', wordWrap: 'break-word' }}>
                                해당 리뷰를 그렇게 작성한 이유를 보다 <br />자세히 적어주세요.<br />최대 4줄로<br />구성가능합니다.
                              </div>
                              <div data-layer="2025.06" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '300', wordWrap: 'break-word' }}>2025.06</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div data-layer="Frame 2147227345" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'inline-flex' }}>
                  {[2, 3].map((idx) => (
                    <div
                      key={idx}
                      onClick={() => navigate?.('/films/the-bat-whispers-1930')}
                      data-layer={idx === 2 ? 'Frame 2147227280' : 'Frame 2147227281'}
                      style={{ width: 830, height: 279, padding: 40, background: 'var(--Gray-50, #F8F8FA)', borderRadius: 20, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 10, display: 'inline-flex', cursor: 'pointer' }}
                    >
                      <div data-layer="Frame 2147227277" style={{ alignSelf: 'stretch', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
                        <div data-layer="Frame 2147227343" style={{ width: 549, justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'flex' }}>
                          <img
                            data-layer="UCH80I8j8DZbiADBlXGQ66se2GecV-OTj-bQoQSuWbU-2ypYVRr2B43aDCiRFGJxxqIGwjnyHRc3Ngh3s5miXQ 1"
                            style={{ width: 159, height: 199, borderRadius: 12, objectFit: 'cover' }}
                            src={reviewImages[idx]}
                            alt="Movie Poster"
                            onError={(e) => { (e.target as HTMLImageElement).src = '/assets/poster_the_bat_whispers-Dg94dkRz.jpg'; }}
                          />
                          <div data-layer="Frame 2147227276" style={{ height: 178, paddingTop: 12, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'inline-flex' }}>
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
                            <div data-layer="Frame 2147227279" style={{ alignSelf: 'stretch', flex: '1 1 0', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'flex' }}>
                              <div data-layer="Frame 2147227278" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'center', gap: 16, display: 'inline-flex' }}>
                                <div data-layer="간단한 제목" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-700, #4A4A53)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>간단한 제목</div>
                              </div>
                              <div data-layer="해당 리뷰를 그렇게 작성한 이유를 보다 자세히 적어주세요. 최대 4줄로 구성가능합니다." style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px', wordWrap: 'break-word' }}>
                                해당 리뷰를 그렇게 작성한 이유를 보다 <br />자세히 적어주세요.<br />최대 4줄로<br />구성가능합니다.
                              </div>
                              <div data-layer="2025.06" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '300', wordWrap: 'break-word' }}>2025.06</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Tab 2: 내가 쓴 글 (1:1 Figma Frame 10) */}
            {activeTab === 'posts' && (
              <div data-layer="Frame 2147227340" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 32, display: 'flex' }}>
                {[1, 2, 3].map((item) => (
                  <div key={item} data-layer={`Frame 214722718${item - 1}`} style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'inline-flex' }}>
                    <div data-layer="Frame 2147227177" style={{ flex: '1 1 0', alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
                      <div data-layer="Frame 2147227292" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 16, display: 'flex' }}>
                        <div data-layer="카테고리" style={{ alignSelf: 'stretch', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Purple-500, #4C22F4)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>카테고리</div>
                        <div data-layer="Frame 2147227291" style={{ flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
                          <div data-layer="제목을 한줄로 구성해서 적어주세요." style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '27px', wordWrap: 'break-word' }}>제목을 한줄로 구성해서 적어주세요.</div>
                          <div data-layer="해당 콘텐츠에 대한 내용을 적어주세요. 최대 2줄로 구성해주세요." style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px', wordWrap: 'break-word' }}>해당 콘텐츠에 대한 내용을 적어주세요.<br />최대 2줄로 구성해주세요.</div>
                        </div>
                      </div>
                      <div data-layer="Frame 2147227285" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 13, display: 'inline-flex' }}>
                        <div data-layer="Frame 2147227210" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 4, display: 'flex' }}>
                          <div data-layer="eye" style={{ width: 16, height: 16, position: 'relative', overflow: 'hidden' }}>
                            <svg width="100%" height="100%" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                              <path d="M1.61342 8.4761C1.52262 8.33234 1.47723 8.26046 1.45182 8.1496C1.43273 8.06632 1.43273 7.93498 1.45182 7.85171C1.47723 7.74084 1.52262 7.66896 1.61341 7.5252C2.36369 6.33721 4.59693 3.33398 8.00027 3.33398C11.4036 3.33398 13.6369 6.33721 14.3871 7.5252C14.4779 7.66896 14.5233 7.74084 14.5487 7.85171C14.5678 7.93498 14.5678 8.06632 14.5487 8.1496C14.5233 8.26046 14.4779 8.33234 14.3871 8.4761C13.6369 9.66409 11.4036 12.6673 8.00027 12.6673C4.59693 12.6673 2.36369 9.66409 1.61342 8.4761Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" />
                              <path d="M8.00027 10.0007C9.10484 10.0007 10.0003 9.10522 10.0003 8.00065C10.0003 6.89608 9.10484 6.00065 8.00027 6.00065C6.8957 6.00065 6.00027 6.89608 6.00027 8.00065C6.00027 9.10522 6.8957 10.0007 8.00027 10.0007Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </div>
                          <div data-layer="1,643" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>1,643</div>
                        </div>
                        <div data-layer="Frame 2147227211" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 4, display: 'flex' }}>
                          <div data-layer="heart" style={{ width: 16, height: 16, position: 'relative', overflow: 'hidden' }}>
                            <svg width="100%" height="100%" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                              <path fillRule="evenodd" clipRule="evenodd" d="M7.99511 3.42388C6.66221 1.8656 4.43951 1.44643 2.76947 2.87334C1.09944 4.30026 0.86432 6.68598 2.17581 8.3736C3.26622 9.77674 6.56619 12.7361 7.64774 13.6939C7.76874 13.801 7.82925 13.8546 7.89982 13.8757C7.96141 13.8941 8.02881 13.8941 8.0904 13.8757C8.16097 13.8546 8.22147 13.801 8.34248 13.6939C9.42403 12.7361 12.724 9.77674 13.8144 8.3736C15.1259 6.68598 14.9195 4.28525 13.2207 2.87334C11.522 1.46144 9.32801 1.8656 7.99511 3.42388Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </div>
                          <div data-layer="1,643" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>1,643</div>
                        </div>
                      </div>
                    </div>
                    <div data-layer="Rectangle 240655222" style={{ width: 180, height: 180, background: '#D9D9D9', borderRadius: 12 }} />
                  </div>
                ))}
              </div>
            )}

            {/* Tab 3: 댓글 단 글 */}
            {activeTab === 'comments' && (
              <div data-layer="Frame 2147227340" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 32, display: 'flex' }}>
                {[1, 2, 3].map((item) => (
                  <div key={item} data-layer={`Frame 214722718${item - 1}`} style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'inline-flex' }}>
                    <div data-layer="Frame 2147227177" style={{ flex: '1 1 0', alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
                      <div data-layer="Frame 2147227292" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 16, display: 'flex' }}>
                        <div data-layer="카테고리" style={{ alignSelf: 'stretch', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Purple-500, #4C22F4)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>카테고리</div>
                        <div data-layer="Frame 2147227291" style={{ flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
                          <div data-layer="제목을 한줄로 구성해서 적어주세요." style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '27px', wordWrap: 'break-word' }}>제목을 한줄로 구성해서 적어주세요.</div>
                          <div data-layer="해당 콘텐츠에 대한 내용을 적어주세요. 최대 2줄로 구성해주세요." style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px', wordWrap: 'break-word' }}>해당 콘텐츠에 대한 내용을 적어주세요.<br />최대 2줄로 구성해주세요.</div>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Tab 4: 찜한 영화 (1:1 Figma Frame 15: 8 MovieCards) */}
            {activeTab === 'likes' && (
              <div data-layer="Frame 2147227197" style={{ width: 1680, display: 'grid', gridTemplateColumns: 'repeat(4, 400px)', columnGap: '26.66px', rowGap: '28px', justifyContent: 'flex-start', alignItems: 'flex-start' }}>
                {likeImages.map((imgSrc, idx) => (
                  <div
                    key={idx}
                    data-layer={idx === 0 || idx === 4 ? 'MovieCard' : `Frame 214722720${idx}`}
                    style={{ width: 400, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'center', gap: 20, display: 'inline-flex' }}
                  >
                    <div data-layer="Frame 2147227300" style={{ width: 400, height: 499, position: 'relative', background: 'white', overflow: 'hidden', borderRadius: 12 }}>
                      <img
                        data-layer="UCH80I8j8DZbiADBlXGQ66se2GecV-OTj-bQoQSuWbU-2ypYVRr2B43aDCiRFGJxxqIGwjnyHRc3Ngh3s5miXQ 1"
                        style={{ width: 400, height: 499, left: 0.25, top: 0, position: 'absolute', objectFit: 'cover' }}
                        src={imgSrc}
                        alt="Movie Poster"
                        onError={(e) => { (e.target as HTMLImageElement).src = '/assets/poster_the_bat_whispers-Dg94dkRz.jpg'; }}
                      />
                    </div>
                    <div data-layer="Frame 2147227224" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'center', gap: 12, display: 'flex' }}>
                      <div data-layer="영화 제목" style={{ alignSelf: 'stretch', textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '21px', wordWrap: 'break-word' }}>영화 제목</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
