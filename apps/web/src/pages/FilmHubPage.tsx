import React, { useEffect, useState, useRef, useCallback } from 'react';
import { filmsApi, revealsApi, proofsApi, profileApi, communityApi } from '../services/apiClient';
import { compareRanking } from '../utils/contentRanking';
import { recordPageView } from '../utils/pageViews';
import { Pagination } from '../components/Pagination';
import { ProofComments } from '../components/ProofComments';
import { CommentSpoiler } from '../components/CommentSpoiler';
import { RatingStars } from '../components/RatingStars';
import { getVisualFixtureFilms, getVisualFixtureReveals, getVisualFixtureMoments, isVisualFixtureMode } from '../testing/useVisualFixture';
import { LoadingState, ErrorState, EmptyState } from '../components/FeedbackStates';
import {
  FilmDetailViewModel,
  RevealItemViewModel,
  ReframeCardViewModel,
  mapFilmDtoToViewModel,
  mapRevealsDtoToViewModel,
  mapProofsDtoToReframeCards,
} from './filmDetailViewModel';
import { mapFilmCatalogResponse } from './filmCatalogViewModel';
import { FilmJourneyControls } from '../components/FilmJourneyControls';
import { RevealTimelineMarkers } from '../components/RevealTimelineMarkers';
import { WatchedAnalysisCard } from '../components/WatchedAnalysisCard';
import { SelectedPortionAnalysis } from '../components/SelectedPortionAnalysis';
import { supportsSelectedPortion } from '../services/selectedPortion';
import { BoxOfficeChart } from '../components/BoxOfficeChart';
import { FilmPicks } from '../components/FilmPicks';
import { ExternalCriticism } from '../components/ExternalCriticism';
import { RankedFilmCard } from '../components/RankedFilmCard';
import { AppModal } from '../components/AppModal';
import { DeleteConfirmation } from '../components/DeleteConfirmation';
import { SortOptions, movieSortOptions } from '../components/SortOptions';
import { useAuth } from '../context/AuthContext';
import { loginDestination, confirmNavigation } from '../utils/navigation';
import { useUnsavedChanges } from '../utils/useUnsavedChanges';
import { saveReviewDraft, takeReviewDraft } from '../utils/reviewDraft';
import { WriteAccessGate } from '../components/WriteAccessGate';
import { DemoFilmNotice } from '../components/DemoFilmNotice';
import '../styles/live-product.css';

interface CastMember {
  id: string;
  name: string;
  role: string;
  image?: string;
  alt?: string;
  ariaLabel?: string;
  isPlaceholder?: boolean;
}

const FIGMA_CAST_MEMBERS: CastMember[] = [
  {
    id: '553:7726',
    name: 'Chester Morris',
    role: 'Detective Anderson',
    image: '/assets/figma-current/film-detail/cast/chester-morris.png',
    alt: 'Portrait of Chester Morris',
  },
  {
    id: '553:7730',
    name: 'Chance Ward',
    role: 'Police Lieutenant',
    isPlaceholder: true,
    ariaLabel: 'Portrait unavailable for Chance Ward',
  },
  {
    id: '553:7734',
    name: 'Una Merkel',
    role: 'Dale Van Gorder',
    image: '/assets/figma-current/film-detail/cast/una-merkel.png',
    alt: 'Portrait of Una Merkel',
  },
  {
    id: '553:7738',
    name: 'Richard Tucker',
    role: 'Mr. Bell',
    image: '/assets/figma-current/film-detail/cast/richard-tucker.png',
    alt: 'Portrait of Richard Tucker',
  },
  {
    id: '553:7742',
    name: 'Whilson Benge',
    role: 'The Butler',
    isPlaceholder: true,
    ariaLabel: 'Portrait unavailable for Whilson Benge',
  },
  {
    id: '553:7746',
    name: 'DeWitt Jennings',
    role: 'Police Captain',
    image: '/assets/figma-current/film-detail/cast/dewitt-jennings.png',
    alt: 'Portrait of DeWitt Jennings',
  },
  {
    id: '553:7750',
    name: "Sidney D'Albrook",
    role: 'Police Sergeant',
    image: '/assets/figma-current/film-detail/cast/sidney-dalbrook.png',
    alt: "Portrait of Sidney D'Albrook",
  },
];

interface CriticReview {
  id: string;
  reviewer: string;
  date: string;
  score: number;
  quote: string;
}

const FIGMA_CRITIC_REVIEWS: CriticReview[] = [
  {
    id: '553:8007',
    reviewer: 'Mordaunt Hall, The New York Times',
    date: '2025.06',
    score: 4,
    quote: '“It is a well-directed film, but … there is nothing new even in this bigger and better Bat.”',
  },
  {
    id: '553:8024',
    reviewer: 'Keith Phipps, The A.V. Club',
    date: '2025.06',
    score: 4,
    quote: '“A dozen or so isolated moments of stunning filmmaking make The Bat Whispers worth a look.”',
  },
  {
    id: '553:8041',
    reviewer: 'TIME Magazine',
    date: '2025.06',
    score: 4,
    quote: '“Size is the only new thing about The Bat Whispers.”',
  },
];
import { ReviewModalPage } from './ReviewModalPage';

export type ReframeCard = ReframeCardViewModel;

const FIGMA_REFRAME_CARDS: readonly ReframeCard[] = [
  {
    id: '1',
    scene: 'SCENE 17',
    timestamp: '[00:33:30]',
    timestampMs: 2010000,
    spoilerCutoffMs: 2010000,
    isLocked: false,
    title: 'The Most Trustworthy Detective Was the Most Dangerous Suspect',
    body: 'Detective Anderson immediately gains everyone’s trust because he carries a badge and appears to represent the law. However, his attempts to control crucial information and monitor the other characters subtly hint at a hidden motive. The final reveal exposes him as the Bat, who attacked the real Anderson and stole his identity.',
    likes: 293,
    comments: 16,
    hasSpoiler: true,
  },
  {
    id: '2',
    scene: 'SCENE 23',
    timestamp: '[00:45:59]',
    timestampMs: 2759000,
    spoilerCutoffMs: 2759000,
    isLocked: false,
    title: 'The Amnesiac Stranger Was the Real Detective',
    body: 'The injured stranger found in the garage cannot explain who he is because of his memory loss. His only memory—trying to make a phone call from the garage—initially seems insignificant. It later reveals that he is the real Detective Anderson, whom the Bat attacked before assuming his identity.',
    likes: 293,
    comments: 16,
    hasSpoiler: true,
  },
  {
    id: '3',
    scene: 'SCENE 31',
    timestamp: '[01:00:45]',
    timestampMs: 3645000,
    spoilerCutoffMs: 3645000,
    isLocked: false,
    title: 'The Missing Blueprint Revealed the Secret Room',
    body: 'The mansion’s blueprint shows a hidden room behind the fireplace. After Richard Fleming is murdered, a torn piece of the blueprint becomes one of the story’s most important clues. It reveals that the mansion’s unusual structure is not merely part of its eerie atmosphere but a hiding place connected to the stolen money and the murders.',
    likes: 293,
    comments: 16,
    hasSpoiler: true,
  },
  {
    id: '4',
    scene: 'SCENE 39',
    timestamp: '[01:10:00]',
    timestampMs: 4200000,
    spoilerCutoffMs: 4200000,
    isLocked: false,
    title: 'Fleming’s Trip Abroad Was Never a Reliable Alibi',
    body: 'Fleming claimed to have been traveling abroad at the time of the initial bank robbery, but railroad ticket receipts recovered from the study indicate he was in town days earlier. This contradiction serves as an early narrative clue linking him directly to the conspiracy.',
    likes: 293,
    comments: 16,
    hasSpoiler: true,
  },
];

const TIMELINE_MARKERS = [
  '/assets/figma-current/film-detail/reframe/marker-leading.svg',
  '/assets/figma-current/film-detail/reframe/marker-leading.svg',
  '/assets/figma-current/film-detail/reframe/marker-leading.svg',
  '/assets/figma-current/film-detail/reframe/marker-active.svg',
  '/assets/figma-current/film-detail/reframe/marker-inactive.svg',
  '/assets/figma-current/film-detail/reframe/marker-inactive.svg',
  '/assets/figma-current/film-detail/reframe/marker-inactive.svg',
  '/assets/figma-current/film-detail/reframe/marker-inactive.svg',
  '/assets/figma-current/film-detail/reframe/marker-inactive.svg',
  '/assets/figma-current/film-detail/reframe/marker-trailing.svg',
  '/assets/figma-current/film-detail/reframe/marker-trailing.svg',
] as const;

interface FilmHubPageProps {
  movieId?: string;
  navigate: (path: string) => void;
}

export const FilmHubPage: React.FC<FilmHubPageProps> = ({ movieId, navigate }) => {
  const { isAuthenticated, user, isAdmin, loading: authLoading } = useAuth();
  const [revealConfirmation, setRevealConfirmation] = useState<{ cutoff: number; movieId: string; editionId: string } | null>(null);
  const [revealSaving, setRevealSaving] = useState(false);
  const [progressSaving, setProgressSaving] = useState(false);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const analysisOpenRef = useRef(false);
  const analysisOwner = useRef('');
  const analysisProgress = useRef(0);
  const [progressRevision, setProgressRevision] = useState(0);
  const [revealError, setRevealError] = useState('');
  const canEditContent = (content: any) => isAuthenticated &&
    content.author_id === user?.id;
  const isDetailView = Boolean(movieId);
  const editionId = new URLSearchParams(window.location.search).get('edition_id') || undefined;

  // --- CATALOG VIEW STATE ---
  const [films, setFilms] = useState<any[]>([]);
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [catalogSort, setCatalogSort] = useState('newest');
  const [catalogPage, setCatalogPage] = useState(1);
  useEffect(() => { setCatalogPage(1); }, [catalogSort, selectedCategory]);
  const [boxOfficePage, setBoxOfficePage] = useState<0 | 1>(0);
  const [showFilmsMoreModal, setShowFilmsMoreModal] = useState(
    typeof window !== 'undefined' && window.location.search.includes('modal=all')
  );

  // --- DETAIL VIEW STATE ---
  const [filmDetail, setFilmDetail] = useState<any>(null);
  const [filmDetailVm, setFilmDetailVm] = useState<FilmDetailViewModel | null>(null);
  const [previewProgressMs, setPreviewProgressMs] = useState<number | null>(null);
  const [filmLoading, setFilmLoading] = useState<boolean>(false);
  const [filmError, setFilmError] = useState<{ status?: number; message?: string } | null>(null);

  const [reveals, setReveals] = useState<any[]>([]);
  const [revealsVm, setRevealsVm] = useState<RevealItemViewModel[]>([]);
  const [selectedReveal, setSelectedReveal] = useState<any>(null);
  const [selectedRevealId, setSelectedRevealId] = useState<string | null>(null);
  const [revealsLoading, setRevealsLoading] = useState<boolean>(false);
  const [revealsError, setRevealsError] = useState<{ status?: number; message?: string } | null>(null);

  const [moments, setMoments] = useState<any[]>([]);
  const [reframeCardsVm, setReframeCardsVm] = useState<ReframeCardViewModel[]>([]);
  const [proofsLoading, setProofsLoading] = useState<boolean>(false);
  const [proofsError, setProofsError] = useState<{ status?: number; message?: string } | null>(null);

  const [revealedSpoilers, setRevealedSpoilers] = useState<{ [key: string]: boolean }>({});

  const activeMovieIdRef = useRef<string | null>(null);
  const activeRevealIdRef = useRef<string | null>(null);
  const filmReqIdRef = useRef(0);
  const revealsReqIdRef = useRef(0);
  const proofsReqIdRef = useRef(0);
  const userEditedProgressRef = useRef(false);

  // Modals
  const [showReviewModal, setShowReviewModal] = useState(
    isVisualFixtureMode() && new URLSearchParams(window.location.search).get('review') === 'true'
  );
  const [selectedReframeModalMoment, setSelectedReframeModalMoment] = useState<any>(null);
  const [reviewRating, setReviewRating] = useState(0);
  const [reviewText, setReviewText] = useState('');
  const [reviewCutoffMinutes, setReviewCutoffMinutes] = useState('');
  const [reviewContainsSpoilers, setReviewContainsSpoilers] = useState(false);
  const [deletingReview, setDeletingReview] = useState<string | null>(null);
  const reviewSubmitting = useRef(false);
  const pendingReviewLikes = useRef(new Set<string>());
  const pendingReviewReveals = useRef(new Set<string>());
  const [revealingReviews, setRevealingReviews] = useState<string[]>([]);
  const reviewRequestKey = useRef<string>(crypto.randomUUID());
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [showReviewToast, setShowReviewToast] = useState(false);

  // Audience Reviews & Community State
  const [publicReviews, setPublicReviews] = useState<any[]>([]);
  const [reviewsLoading, setReviewsLoading] = useState<boolean>(false);
  const [reviewsLoadedFor, setReviewsLoadedFor] = useState('');
  const reviewsRequestId = useRef(0);
  const [reviewsError, setReviewsError] = useState<string | null>(null);
  const [reviewSort, setReviewSort] = useState<'popular' | 'recent'>('recent');
  const [editingPost, setEditingPost] = useState<{ id: string; version_no: number } | null>(null);
  const ownReview = publicReviews.find(post => post.author_id === user?.id && post.rating != null);
  const reviewBaseline = useRef('');
  const reviewSnapshot = JSON.stringify([reviewText, reviewRating, reviewContainsSpoilers]);
  const reviewDirty = showReviewModal && reviewSnapshot !== reviewBaseline.current && !!(reviewText || reviewRating || reviewContainsSpoilers);
  const preserveReview = () => saveReviewDraft(movieId || 'the-bat-whispers-1930', {
    owner: user?.id || null, rating: reviewRating, text: reviewText,
    containsSpoilers: reviewContainsSpoilers, editing: editingPost,
    requestKey: reviewRequestKey.current, savedAt: Date.now(),
  });
  useUnsavedChanges(reviewDirty, preserveReview);
  useEffect(() => {
    if (authLoading || !movieId) return;
    const draft = takeReviewDraft(movieId, user?.id || null);
    if (!draft) return;
    setReviewText(draft.text); setReviewRating(draft.rating);
    setReviewContainsSpoilers(draft.containsSpoilers); setEditingPost(draft.editing);
    reviewRequestKey.current = draft.requestKey; setShowReviewModal(true);
  }, [authLoading, movieId, user?.id]);
  const closeReview = useCallback(() => {
    if (reviewSubmitting.current) return;
    if (reviewDirty && !window.confirm('Discard your unsaved review?')) return;
    setShowReviewModal(false);
  }, [reviewDirty]);

  // Comments thread state
  const [expandedCommentsPostId, setExpandedCommentsPostId] = useState<string | null>(null);
  const [shareToast, setShareToast] = useState<string | null>(null);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get('reviewId');
    if (!requested || reviewsLoading) return;
    document.getElementById(`review-${requested}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [publicReviews, reviewsLoading]);
  const [activeCardIndex, setActiveCardIndex] = useState<number | null>(null);
  const pendingTimelineScroll = useRef(false);
  useEffect(() => {
    if (proofsLoading || !pendingTimelineScroll.current || !reframeCardsVm.length) return;
    const target = document.querySelector('[data-testid="film-detail-reframe-card-0"]');
    if (target) { target.scrollIntoView({ behavior: 'smooth', block: 'center' }); pendingTimelineScroll.current = false; }
  }, [proofsLoading, reframeCardsVm]);

  // Load Catalog Data
  useEffect(() => {
    let isMounted = true;
    async function loadCatalog() {
      const fixtureFilms = getVisualFixtureFilms();
      if (fixtureFilms) {
        setFilms(fixtureFilms);
        return;
      }
      try {
        const res = await filmsApi.getAllFilms();
        if (isMounted) {
          const parsed = mapFilmCatalogResponse(res);
          if (parsed.success) {
            setFilms(parsed.films);
          } else {
            setFilms([]);
          }
        }
      } catch {
        if (isMounted) setFilms([]);
      }
    }
    if (!isDetailView) {
      loadCatalog();
    }
    return () => { isMounted = false; };
  }, [isDetailView]);

  const loadFilmDetail = useCallback(async (targetMovieId: string, currentReq: number) => {
    setFilmLoading(true);
    setFilmError(null);
    try {
      const res = await filmsApi.getFilm(targetMovieId, editionId);
      // Ownership check: must match active target movie and request generation
      if (activeMovieIdRef.current !== targetMovieId || filmReqIdRef.current !== currentReq) {
        return;
      }
      const vm = mapFilmDtoToViewModel(res);
      if (!vm) {
        setFilmDetailVm(null);
        setFilmError({ message: 'Malformed film data' });
      } else {
        setFilmDetailVm(vm);
        setFilmDetail(res.data);
        void recordPageView('films', res.data.movie_id);
        if (!userEditedProgressRef.current) {
          setPreviewProgressMs(res.data?.viewer_progress_ms ?? 0);
        }
        setFilmError(null);
      }
    } catch (err: any) {
      if (activeMovieIdRef.current !== targetMovieId || filmReqIdRef.current !== currentReq) {
        return;
      }
      setFilmDetailVm(null);
      setFilmError({ status: err?.status, message: err?.message || 'Failed to load film detail' });
    } finally {
      if (activeMovieIdRef.current === targetMovieId && filmReqIdRef.current === currentReq) {
        setFilmLoading(false);
      }
    }
  }, [editionId]);

  const closeAnalysis = () => {
    analysisOpenRef.current = false;
    setAnalysisOpen(false);
    ++revealsReqIdRef.current;
    ++proofsReqIdRef.current;
    activeRevealIdRef.current = null;
    setSelectedRevealId(null);
    setRevealsVm([]);
    setReframeCardsVm([]);
    setRevealsLoading(false);
    setProofsLoading(false);
    setRevealsError(null);
    setProofsError(null);
  };

  const loadProofsForReveal = useCallback(async (
    targetMovieId: string,
    targetRevealId: string,
    currentReq: number
  ) => {
    if (!analysisOpenRef.current) return;
    setProofsLoading(true);
    setProofsError(null);
    setReframeCardsVm([]);
    try {
      const res = await proofsApi.getProofsForReveal(targetRevealId, true);
      // Strict ownership and generation check:
      if (
        !analysisOpenRef.current || activeMovieIdRef.current !== targetMovieId ||
        activeRevealIdRef.current !== targetRevealId ||
        proofsReqIdRef.current !== currentReq
      ) {
        return;
      }
      const cards = mapProofsDtoToReframeCards(res);
      if (!cards) {
        setReframeCardsVm([]);
        setProofsError({ message: 'Malformed proofs data' });
      } else {
        setReframeCardsVm(cards);
        setProofsError(null);
      }
    } catch (err: any) {
      if (
        activeMovieIdRef.current !== targetMovieId ||
        activeRevealIdRef.current !== targetRevealId ||
        proofsReqIdRef.current !== currentReq
      ) {
        return;
      }
      setReframeCardsVm([]);
      setProofsError({ status: err?.status, message: err?.message || 'Failed to load proofs' });
    } finally {
      if (
        activeMovieIdRef.current === targetMovieId &&
        activeRevealIdRef.current === targetRevealId &&
        proofsReqIdRef.current === currentReq
      ) {
        setProofsLoading(false);
      }
    }
  }, []);

  const loadReveals = useCallback(async (targetMovieId: string, currentReq: number) => {
    if (!analysisOpenRef.current) return;
    setRevealsLoading(true);
    setRevealsError(null);
    try {
      const res = await revealsApi.getReveals(targetMovieId, editionId, true);
      if (activeMovieIdRef.current !== targetMovieId || revealsReqIdRef.current !== currentReq) {
        return;
      }
      const mapped = mapRevealsDtoToViewModel(res);
      const vms = mapped?.filter(reveal => !reveal.isLocked && reveal.timestampDisplay && analysisProgress.current > 0 &&
        Math.max(reveal.timestampMs, reveal.spoilerCutoffMs) <= analysisProgress.current);
      if (!vms) {
        setRevealsVm([]);
        setSelectedRevealId(null);
        activeRevealIdRef.current = null;
        ++proofsReqIdRef.current;
        setReframeCardsVm([]);
        setProofsLoading(false);
        setProofsError(null);
        setRevealsError({ message: 'Malformed reveals data' });
      } else {
        setRevealsVm(vms);
        setRevealsError(null);
        if (vms.length > 0) {
          const preservedId = (activeRevealIdRef.current && vms.some(v => v.revealId === activeRevealIdRef.current))
            ? activeRevealIdRef.current
            : vms[0].revealId;
          setSelectedRevealId(preservedId);
          activeRevealIdRef.current = preservedId;
          const proofReq = ++proofsReqIdRef.current;
          loadProofsForReveal(targetMovieId, preservedId, proofReq);
        } else {
          // Empty reveals: zero proof requests
          setSelectedRevealId(null);
          activeRevealIdRef.current = null;
          ++proofsReqIdRef.current;
          setReframeCardsVm([]);
          setProofsLoading(false);
          setProofsError(null);
        }
      }
    } catch (err: any) {
      if (activeMovieIdRef.current !== targetMovieId || revealsReqIdRef.current !== currentReq) {
        return;
      }
      setRevealsVm([]);
      setSelectedRevealId(null);
      activeRevealIdRef.current = null;
      ++proofsReqIdRef.current;
      setReframeCardsVm([]);
      setProofsLoading(false);
      setProofsError(null);
      setRevealsError({ status: err?.status, message: err?.message || 'Failed to load reveals' });
    } finally {
      if (activeMovieIdRef.current === targetMovieId && revealsReqIdRef.current === currentReq) {
        setRevealsLoading(false);
      }
    }
  }, [loadProofsForReveal, editionId]);

  const retryFilm = () => {
    const targetMovieId = movieId || 'the-bat-whispers-1930';
    activeMovieIdRef.current = targetMovieId;
    const currentReq = ++filmReqIdRef.current;
    loadFilmDetail(targetMovieId, currentReq);
  };

  const retryReveals = () => {
    const targetMovieId = movieId || 'the-bat-whispers-1930';
    activeMovieIdRef.current = targetMovieId;
    const currentReq = ++revealsReqIdRef.current;
    loadReveals(targetMovieId, currentReq);
  };

  const retryProofs = () => {
    const targetMovieId = movieId || 'the-bat-whispers-1930';
    if (selectedRevealId && activeMovieIdRef.current === targetMovieId) {
      activeRevealIdRef.current = selectedRevealId;
      const currentReq = ++proofsReqIdRef.current;
      loadProofsForReveal(targetMovieId, selectedRevealId, currentReq);
    }
  };

  const confirmReveal = async () => {
    if (!revealConfirmation || revealSaving) return;
    const target = revealConfirmation;
    setRevealSaving(true);
    setRevealError('');
    try {
      const progress = Math.max(target.cutoff, filmDetail?.viewer_progress_ms || 0);
      await profileApi.updateWatchProgress(target.movieId, {
        edition_id: target.editionId, progress_ms: progress,
        state: progress >= (filmDetailVm?.runtimeMs || Infinity) ? 'COMPLETED' : 'IN_PROGRESS',
        completed_reveal_ids: [],
      });
      if (activeMovieIdRef.current !== target.movieId) return;
      userEditedProgressRef.current = true;
      setPreviewProgressMs(progress);
      setProgressRevision(value => value + 1);
      await Promise.all([
        loadFilmDetail(target.movieId, ++filmReqIdRef.current),
        loadReveals(target.movieId, ++revealsReqIdRef.current),
      ]);
      setRevealConfirmation(null);
    } catch {
      setRevealError('The viewing position could not be saved. Content remains protected. Please try again.');
    } finally { setRevealSaving(false); }
  };

  const loadPublicReviews = useCallback(async (targetMovieId: string, sort: 'popular' | 'recent' = reviewSort) => {
    const requestId = ++reviewsRequestId.current;
    setReviewsLoadedFor('');
    setReviewsLoading(true);
    setReviewsError(null);
    try {
      const res = await communityApi.listPosts(targetMovieId, undefined, sort);
      if (requestId !== reviewsRequestId.current || targetMovieId !== activeMovieIdRef.current) return;
      if (res && res.data) {
        setPublicReviews(res.data.filter((post: any) => Number.isInteger(post.rating) && post.rating >= 1 && post.rating <= 5));
      } else {
        setPublicReviews([]);
      }
      setReviewsLoadedFor(`${targetMovieId}:${user?.id || 'guest'}`);
    } catch (err: any) {
      if (requestId !== reviewsRequestId.current || targetMovieId !== activeMovieIdRef.current) return;
      setReviewsError(err?.message || 'Failed to load public reviews');
      setPublicReviews([]);
    } finally {
      if (requestId === reviewsRequestId.current && targetMovieId === activeMovieIdRef.current) setReviewsLoading(false);
    }
  }, [reviewSort, user?.id]);

  // Load Detail Data
  useEffect(() => {
    if (!isDetailView) return;

    if (isVisualFixtureMode()) {
      const fixtureFilms = getVisualFixtureFilms();
      const fixtureReveals = getVisualFixtureReveals();
      const fixtureMoments = getVisualFixtureMoments();

      if (fixtureFilms && fixtureReveals) {
        setFilmDetail({
          title: 'The Bat Whispers',
          release_year: 1930,
          duration_mins: 82,
          rating_code: 'NR',
          synopsis: 'A mysterious criminal known as “The Bat” announces his retirement before carrying out a daring bank robbery. Meanwhile, a group of people gathers at an isolated country mansion, unaware that the stolen money may be hidden somewhere inside. As strange events unfold and the guests begin to suspect one another, Detective Anderson races to uncover the truth and reveal the identity of the elusive criminal.'
        });
        setReveals(fixtureReveals);
        if (fixtureReveals.length > 0) setSelectedReveal(fixtureReveals[0]);
        if (fixtureMoments) setMoments(fixtureMoments);
        return;
      }
    }

    const targetMovieId = movieId || 'the-bat-whispers-1930';

    // Set active IDs
    activeMovieIdRef.current = targetMovieId;
    activeRevealIdRef.current = null;

    // Increment generations to invalidate all prior in-flight requests
    const filmReq = ++filmReqIdRef.current;
    ++revealsReqIdRef.current;
    ++proofsReqIdRef.current;

    // Clear previous movie's metadata and progress immediately so it doesn't appear for new movie
    analysisOpenRef.current = false;
    setAnalysisOpen(false);
    userEditedProgressRef.current = false;
    setPreviewProgressMs(null);
    setActiveCardIndex(null);
    setFilmDetailVm(null);
    setFilmError(null);

    setRevealsVm([]);
    setRevealsError(null);
    setSelectedRevealId(null);

    setReframeCardsVm([]);
    setProofsError(null);
    setProofsLoading(false);

    loadFilmDetail(targetMovieId, filmReq);
    setRevealsLoading(false);
    loadPublicReviews(targetMovieId, reviewSort);
  }, [isDetailView, movieId, loadFilmDetail, loadReveals, loadPublicReviews, reviewSort]);

  const handleSortChange = (newSort: 'popular' | 'recent') => {
    setReviewSort(newSort);
    const targetMovieId = movieId || 'the-bat-whispers-1930';
    loadPublicReviews(targetMovieId, newSort);
  };

  const handleToggleSpoiler = (id: string) => {
    setRevealedSpoilers(prev => ({ ...prev, [id]: !prev[id] }));
  };

  useEffect(() => {
    if (!showReviewModal) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const dialog = document.querySelector<HTMLElement>('[data-testid="review-modal-content"]');
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled), textarea:not(:disabled), input:not(:disabled), [tabindex="0"]') || []);
    focusable()[0]?.focus();
    const trapFocus = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      const items = focusable();
      const first = items[0], last = items[items.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || !dialog?.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog?.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    };
    document.addEventListener('keydown', trapFocus);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', trapFocus);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [showReviewModal]);

  // Escape key handler for accessible modal dismissal (R02)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showReviewModal) closeReview();
        setShowFilmsMoreModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showReviewModal, closeReview]);

  const handleSaveReview = async () => {
    if (authLoading) return;
    if (!isAuthenticated) { preserveReview(); navigate(loginDestination()); return; }
    if (!reviewText.trim() || reviewRating < 1 || reviewSubmitting.current) return;
    reviewSubmitting.current = true;
    setIsSubmittingReview(true);
    setReviewError(null);

    const targetMovieId = movieId || 'the-bat-whispers-1930';

    try {
      if (editingPost) {
        await communityApi.updatePost(editingPost.id, {
          title: `Audience Review (${reviewRating}/5 Stars)`,
          body_markdown: reviewText,
          expected_version: editingPost.version_no,
          rating: reviewRating,
          contains_spoilers: reviewContainsSpoilers,
          author_cutoff_ms: reviewCutoffMinutes === '' ? undefined : Math.round(Number(reviewCutoffMinutes) * 60000),
        });
      } else {
        await communityApi.createPost({
          idempotency_key: reviewRequestKey.current,
          work_id: targetMovieId,
          edition_id: filmDetailVm?.editionId || editionId,
          title: `Audience Review (${reviewRating}/5 Stars)`,
          body_markdown: reviewText,
          content_type: 'REVIEW',
          rating: reviewRating,
          contains_spoilers: reviewContainsSpoilers,
          author_cutoff_ms: reviewCutoffMinutes === '' ? undefined : Math.round(Number(reviewCutoffMinutes) * 60000),
        });
      }

      setShowReviewModal(false);
      setReviewText('');
      setReviewRating(0);
      setReviewContainsSpoilers(false);
      setReviewCutoffMinutes('');
      reviewRequestKey.current = crypto.randomUUID();
      setEditingPost(null);
      setShowReviewToast(true);
      await loadPublicReviews(targetMovieId, reviewSort);
      loadFilmDetail(targetMovieId, ++filmReqIdRef.current);
    } catch (err: any) {
      if (err?.status === 401) { preserveReview(); navigate(loginDestination()); return; }
      if (err?.status === 409 || err?.message?.includes('409') || err?.message?.includes('Conflict')) {
        setReviewError('Conflict: This review was modified in another session. Please refresh to see the latest version.');
      } else {
        setReviewError(err?.message || 'An error occurred while saving the review.');
      }
    } finally {
      reviewSubmitting.current = false;
      setIsSubmittingReview(false);
    }
  };

  const openNewReview = () => {
    if ((authLoading || (isAuthenticated && reviewsLoading)) && !isVisualFixtureMode()) return;
    if (!isAuthenticated && !isVisualFixtureMode()) {
      navigate(loginDestination(`/films/${encodeURIComponent(movieId || 'the-bat-whispers-1930')}?review=true`));
      return;
    }
    if (ownReview) { void handleStartEditReview(ownReview); return; }
    setEditingPost(null); setReviewText(''); setReviewRating(0);
    setReviewContainsSpoilers(false); reviewBaseline.current = JSON.stringify(['', 0, false]);
    setReviewCutoffMinutes(''); setReviewError(null);
    reviewRequestKey.current = crypto.randomUUID(); setShowReviewModal(true);
  };

  const handleDeleteReview = async (postId: string) => {
    const post = publicReviews.find(p => (p.post_id || p.id) === postId);
    if (!post || !canEditContent(post)) return;
    const targetMovieId = movieId || 'the-bat-whispers-1930';
    await communityApi.deletePost(postId);
    await loadPublicReviews(targetMovieId, reviewSort);
    loadFilmDetail(targetMovieId, ++filmReqIdRef.current);
  };

  const handleStartEditReview = async (post: any) => {
    if (!canEditContent(post)) return;
    const id = post.post_id || post.id;
    try {
      if (post.is_spoiler_masked || post.is_locked) {
        if (!window.confirm('Reveal this review before editing? It may contain spoilers.')) return;
        await communityApi.unlockContent('POST', id, post.version_no || 1);
      }
      const response = await communityApi.getPost(id);
      const current = response.data;
      if (current.is_spoiler_masked || current.is_locked || typeof current.body_markdown !== 'string') throw new Error('Reveal the review before editing.');
      setReviewError(null);
      setEditingPost({ id, version_no: current.version_no || post.version_no || 1 });
      setReviewText(current.body_markdown);
      setReviewRating(current.rating || 5);
      setReviewContainsSpoilers(Boolean(current.contains_spoilers));
      reviewBaseline.current = JSON.stringify([current.body_markdown, current.rating || 5, Boolean(current.contains_spoilers)]);
      setReviewCutoffMinutes(current.author_cutoff_ms == null ? '' : String(current.author_cutoff_ms / 60000));
      setShowReviewModal(true);
    } catch (err: any) { alert(err?.message || 'Could not load review for editing.'); }
  };

  const editOnReturn = useRef<string | null>(null);
  useEffect(() => {
    if (reviewsLoading || authLoading) return;
    if (new URLSearchParams(window.location.search).get('review') !== 'true') return;
    const key = `${movieId}:${user?.id || 'guest'}`;
    if (editOnReturn.current === key || reviewsLoadedFor !== key) return;
    editOnReturn.current = key;
    if (editingPost || reviewText || reviewRating) return;
    if (!isAuthenticated) { navigate(loginDestination()); return; }
    if (ownReview) void handleStartEditReview(ownReview);
    else setShowReviewModal(true);
  }, [ownReview, reviewsLoading, reviewsLoadedFor, authLoading, movieId, user?.id, editingPost, reviewText, reviewRating]);

  const handleToggleReviewLike = async (postId: string, currentLiked: boolean) => {
    if (!isAuthenticated) { navigate(loginDestination()); return; }
    if (pendingReviewLikes.current.has(postId)) return;
    pendingReviewLikes.current.add(postId);
    const original = publicReviews.find(post => (post.post_id || post.id) === postId);
    const nextLiked = !currentLiked;
    setPublicReviews(prev => prev.map(p => {
      if ((p.post_id || p.id) === postId) {
        return {
          ...p,
          viewer_liked: nextLiked,
          like_count: Math.max(0, (p.like_count || 0) + (nextLiked ? 1 : -1))
        };
      }
      return p;
    }));
    try {
      await communityApi.putReaction(postId, nextLiked);
    } catch (err: any) {
      setPublicReviews(previous => previous.map(post => (post.post_id || post.id) === postId && original ? original : post));
      setShareToast('Could not update your like. Please try again.');
    } finally {
      pendingReviewLikes.current.delete(postId);
    }
  };

  const handleUnlockReview = async (postId: string, versionNo: number = 1) => {
    if (pendingReviewReveals.current.has(postId)) return;
    pendingReviewReveals.current.add(postId);
    setRevealingReviews(previous => [...previous, postId]);
    try {
      await communityApi.unlockContent('POST', postId, versionNo);
      const targetMovieId = movieId || 'the-bat-whispers-1930';
      await loadPublicReviews(targetMovieId, reviewSort);
    } catch (err: any) {
      setShareToast('Could not reveal this review. Please try again.');
    } finally {
      pendingReviewReveals.current.delete(postId);
      setRevealingReviews(previous => previous.filter(id => id !== postId));
    }
  };

  const handleSharePost = (postId: string) => {
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const shareUrl = `${origin}/films/${encodeURIComponent(movieId || 'the-bat-whispers-1930')}?reviewId=${encodeURIComponent(postId)}`;
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(shareUrl).then(() => {
        setShareToast(`Post link copied to clipboard: ${shareUrl}`);
        setTimeout(() => setShareToast(null), 3500);
      }).catch(() => {
        setShareToast(`Post link: ${shareUrl}`);
        setTimeout(() => setShareToast(null), 3500);
      });
    } else {
      setShareToast(`Post link: ${shareUrl}`);
      setTimeout(() => setShareToast(null), 3500);
    }
  };

  const handleToggleComments = (postId: string) => {
    if (expandedCommentsPostId && !confirmNavigation(window.location.pathname + window.location.search)) return;
    setExpandedCommentsPostId(value => value === postId ? null : postId);
  };

  // --------------------------------------------------------------------------
  // 1. DETAIL VIEW (1:1 Figma Frame 13:30696)
  // --------------------------------------------------------------------------
  if (isDetailView) {
    const isVisualFixture = isVisualFixtureMode();

    if (isVisualFixture && showReviewModal) {
      return <ReviewModalPage onClose={() => setShowReviewModal(false)} navigate={navigate} />;
    }

    const savedProgress = Math.max(0, Number(filmDetail?.viewer_progress_ms) || 0);
    const safeProgress = Math.min(savedProgress, previewProgressMs ?? savedProgress);
    const separatedAnalysis = supportsSelectedPortion(filmDetailVm?.movieId || '', filmDetailVm?.editionId || '');
    const showAnalysis = analysisOpen && analysisOwner.current === `${movieId}:${editionId || ''}`;
    const watchedReveals = revealsVm.filter(reveal => !reveal.isLocked && safeProgress > 0 &&
      Math.max(reveal.timestampMs, reveal.spoilerCutoffMs) <= safeProgress);
    const reframeCards: readonly ReframeCard[] = isVisualFixture
      ? FIGMA_REFRAME_CARDS
      : reframeCardsVm.filter(card => showAnalysis && watchedReveals.some(reveal => reveal.revealId === selectedRevealId) &&
          !card.isLocked && safeProgress > 0 && typeof card.spoilerCutoffMs === 'number' &&
          Number.isFinite(card.spoilerCutoffMs) && card.spoilerCutoffMs >= 0 && card.spoilerCutoffMs <= safeProgress &&
          (card.timestampMs == null || card.timestampMs <= safeProgress));

    const isBatWhispers = isVisualFixture || (filmDetailVm?.movieId || movieId) === 'the-bat-whispers-1930';

    return (
      <div className={isVisualFixture ? undefined : 'live-film-detail'} data-layer="Film - Detail Page" style={{ width: 1920, position: 'relative', background: 'var(--Gray-0, white)', display: 'flex', flexDirection: 'column' }}>
        {/* Top Hero Section (571px high relative container, Y=90..661) */}
        <div data-testid="film-detail-hero" style={{ width: 1920, height: 571, position: 'relative', overflow: 'hidden' }}>
          {/* Top Backdrop (Y=90 in Figma -> top=0) */}
          {isBatWhispers ? (
            <img
              data-testid="film-detail-backdrop"
              data-layer="Screenshot-Backdrop"
              style={{ width: 1930, height: 771, left: -10, top: 0, position: 'absolute', objectFit: 'cover' }}
              src="/assets/2026-08-21-10-33-46-1-84-12618.png"
              alt="Backdrop"
              onError={(e) => { (e.target as HTMLImageElement).src = '/assets/backdrop_the_bat_whispers-D29gN3z0.png'; }}
            />
          ) : (
            <div
              data-testid="film-detail-backdrop"
              style={{
                width: 1930,
                height: 771,
                left: -10,
                top: 0,
                position: 'absolute',
                background: 'linear-gradient(135deg, #1A1D2E 0%, #0F111A 50%, #05060A 100%)',
              }}
            />
          )}
          {/* Gradient Overlay (Y=201 in Figma -> top=111) */}
          <div
            data-testid="film-detail-gradient"
            data-layer="Rectangle 240655235"
            style={{ width: 1920, height: 503, left: 0, top: 111, position: 'absolute', background: 'linear-gradient(180deg, rgba(255, 255, 255, 0) 0%, rgba(255, 255, 255, 1) 71.3253%, #FFFFFF 100%)' }}
          />

          {/* Poster & Meta Area (Y=246 in Figma -> top=156) */}
          <div
            data-testid="film-detail-hero-content"
            data-layer="Frame 2147227248"
            style={{ width: 1920, paddingLeft: 120, paddingRight: 120, left: 0, top: 156, position: 'absolute', boxSizing: 'border-box', justifyContent: 'flex-start', alignItems: 'flex-end', gap: 46, display: 'inline-flex' }}
          >
            {isBatWhispers ? (
              <img
                data-testid="film-detail-poster"
                data-layer="Batwhispers 1"
                style={{ width: 283, height: 415, borderRadius: 12, objectFit: 'cover', flexShrink: 0 }}
                src={isVisualFixture ? '/assets/batwhispers-1-84-12615.png' : '/assets/catalog/wikidata/Q3985804-english-b7da81ff.jpg'}
                alt="Batwhispers 1"
                onError={(e) => { (e.target as HTMLImageElement).src = '/assets/poster_the_bat_whispers-Dg94dkRz.jpg'; }}
              />
            ) : filmDetailVm?.posterPath ? (
              <img
                data-testid="film-detail-poster"
                data-layer="Poster"
                style={{ width: 283, height: 415, borderRadius: 12, objectFit: 'cover', flexShrink: 0 }}
                src={filmDetailVm.posterPath}
                alt={`${filmDetailVm.title} Poster`}
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div
                data-testid="film-detail-poster"
                role="img"
                aria-label={`${filmDetailVm?.title || 'Film'} poster unavailable`}
                style={{
                  width: 283,
                  height: 415,
                  borderRadius: 12,
                  background: '#2D2D34',
                  color: '#898992',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 12,
                  flexShrink: 0,
                  fontSize: 16,
                  fontFamily: 'Pretendard',
                }}
              >
                <span style={{ fontSize: 40 }}>🎬</span>
                <span>Poster unavailable</span>
              </div>
            )}
            <div data-layer="Frame 2147227247" style={{ flex: '1 1 0', minWidth: 0, justifyContent: 'space-between', alignItems: 'flex-start', display: 'flex', gap: 24 }}>
              <div data-testid="film-detail-meta" data-layer="Frame 2147227246" style={{ width: 1031, height: 191, paddingBottom: 20, boxSizing: 'border-box', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
                {!isVisualFixture && filmError ? (
                  <div style={{ alignSelf: 'stretch' }}>
                    <ErrorState
                      title="Failed to Load Film"
                      message={filmError.message || 'Unable to retrieve film metadata.'}
                      statusCode={filmError.status}
                      onRetry={retryFilm}
                    />
                  </div>
                ) : (
                  <div data-layer="Frame 2147227243" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 40, display: 'flex' }}>
                    <div data-layer="Frame 2147227230" style={{ alignSelf: 'stretch', height: 68, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'flex' }}>
                      <div data-testid="film-detail-title" data-layer="The Bat Whispers" style={{ alignSelf: 'stretch', minHeight: 39, justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'black', fontSize: 28, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 600, lineHeight: '39.2px' }}>
                        {isVisualFixture
                          ? (filmDetail?.title || 'The Bat Whispers')
                          : (filmDetailVm
                              ? filmDetailVm.title
                              : (filmLoading ? 'Loading film details...' : ''))}
                      </div>
                      <div data-layer="Frame 2147227240" style={{ height: 17, justifyContent: 'flex-start', alignItems: 'center', gap: 12, display: 'inline-flex' }}>
                        <div data-layer="Frame 2147227241" style={{ height: 17, paddingRight: 12, borderRight: '1px var(--Gray-400, #AFAFB8) solid', justifyContent: 'center', alignItems: 'center', display: 'flex' }}>
                          <div data-layer="1930" style={{ color: 'black', fontSize: 14, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 400, lineHeight: '16.7px' }}>
                            {isVisualFixture
                              ? (filmDetail?.release_year || '1930')
                              : (filmDetailVm?.year || '')}
                          </div>
                        </div>
                        <div data-layer="Frame 2147227242" style={{ height: 17, paddingRight: 12, borderRight: '1px var(--Gray-400, #AFAFB8) solid', justifyContent: 'center', alignItems: 'center', display: 'flex' }}>
                          <div data-layer="82min" style={{ color: 'black', fontSize: 14, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 400, lineHeight: '16.7px' }}>
                            {isVisualFixture
                              ? (filmDetail?.duration_mins ? `${filmDetail.duration_mins}min` : '82min')
                              : (filmDetailVm?.runtimeDisplay || '')}
                          </div>
                        </div>
                        {filmDetailVm?.director ? (
                          <div data-testid="film-detail-director" style={{ height: 17, paddingRight: 12, borderRight: '1px var(--Gray-400, #AFAFB8) solid', justifyContent: 'center', alignItems: 'center', display: 'flex' }}>
                            <div style={{ color: 'black', fontSize: 14, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 400, lineHeight: '16.7px' }}>
                              Director: {filmDetailVm.director}
                            </div>
                          </div>
                        ) : null}
                        {isVisualFixture ? (
                          <div data-layer="NR" style={{ color: 'black', fontSize: 14, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 400, lineHeight: '16.7px' }}>
                            {filmDetail?.rating_code || 'NR'}
                          </div>
                        ) : filmDetailVm?.ratingCode ? (
                          <div data-layer="NR" style={{ color: 'black', fontSize: 14, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 400, lineHeight: '16.7px' }}>
                            {filmDetailVm.ratingCode}
                          </div>
                        ) : null}
                      </div>
                    </div>
                    <div id="film-synopsis" data-testid="film-detail-synopsis" data-layer="A mysterious criminal..." style={{ alignSelf: 'stretch', flexShrink: 0, overflowWrap: 'anywhere', color: 'black', fontSize: 14, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 400, lineHeight: '21px' }}>
                      {isVisualFixture
                        ? (filmDetail?.synopsis || 'A mysterious criminal known as “The Bat” announces his retirement before carrying out a daring bank robbery. Meanwhile, a group of people gathers at an isolated country mansion, unaware that the stolen money may be hidden somewhere inside. As strange events unfold and the guests begin to suspect one another, Detective Anderson races to uncover the truth and reveal the identity of the elusive criminal.')
                        : (filmDetailVm?.synopsis || '')}
                    </div>
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <button
                type="button"
                onClick={openNewReview}
                aria-label={ownReview ? 'Edit My Review' : 'Write a Review'}
                disabled={(authLoading || (isAuthenticated && reviewsLoading)) && !isVisualFixtureMode()}
                data-testid="film-detail-review-button"
                data-layer="AppButton"
                style={{
                  width: 193,
                  height: 58,
                  padding: '16px 20px',
                  background: 'var(--Purple-500, #4C22F4)',
                  borderRadius: 20,
                  border: 'none',
                  margin: 0,
                  boxSizing: 'border-box',
                  justifyContent: 'center',
                  alignItems: 'center',
                  gap: 8,
                  display: 'flex',
                  cursor: 'pointer',
                  flexShrink: 0,
                }}
              >
                <div data-layer="edit-02" style={{ width: 24, height: 24, position: 'relative', overflow: 'hidden', flexShrink: 0 }}>
                  <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M18 10.0003L14 6.0003M2.5 21.5003L5.88437 21.1243C6.29786 21.0783 6.5046 21.0553 6.69785 20.9928C6.86929 20.9373 7.03245 20.8589 7.18289 20.7597C7.35245 20.6479 7.49955 20.5008 7.79373 20.2066L21 7.0003C22.1046 5.89573 22.1046 4.10487 21 3.0003C19.8955 1.89573 18.1046 1.89573 17 3.0003L3.79373 16.2066C3.49955 16.5008 3.35246 16.6478 3.24064 16.8174C3.14143 16.9679 3.06301 17.131 3.00751 17.3025C2.94496 17.4957 2.92198 17.7024 2.87604 18.1159L2.5 21.5003Z" stroke="var(--Gray-0, white)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <span data-layer="Write a Review" style={{ textAlign: 'center', color: 'white', fontSize: 18, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 500, lineHeight: '26px' }}>
                  {ownReview ? 'Edit My Review' : 'Write a Review'}
                </span>
              </button>
              </div>
            </div>
          </div>
        </div>

        {/* Lower Content Flow (Starts at Y=661) */}
        <div
          data-layer="Frame 2147227286"
          style={{ width: 1920, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}
        >
          <div
            data-testid="film-detail-rating-band"
            data-layer="Frame 2147227251"
            style={{ alignSelf: 'stretch', width: 1920, height: 181, boxSizing: 'border-box', paddingTop: 60, paddingBottom: 40, paddingLeft: 120, paddingRight: 120, background: '#FFFFFF', borderBottom: '1px var(--Gray-100, #F2F2F5) solid', justifyContent: 'space-between', alignItems: 'flex-start', display: 'flex' }}
          >
            <div data-testid="film-detail-average-rating" data-layer="Frame 2147227250" style={{ width: 180, height: 80, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 16, display: 'inline-flex' }}>
              <div data-layer="Average Rating" style={{ alignSelf: 'stretch', height: 24, justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-700, #4A4A53)', fontSize: 20, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 600, lineHeight: '24px' }}>Average Rating</div>
              <div data-layer="Frame 2147227249" style={{ alignSelf: 'stretch', height: 40, justifyContent: 'flex-start', alignItems: 'center', gap: 6, display: 'inline-flex' }}>
                <div data-layer="Star 3" style={{ width: 34, height: 32, background: 'transparent', flexShrink: 0 }}>
                  <svg width="100%" height="100%" viewBox="0 0 34 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M14.639 1.19432C15.425 -0.398347 17.6961 -0.398347 18.4821 1.19432L21.9398 8.20038C22.252 8.83283 22.8553 9.27119 23.5533 9.37261L31.2849 10.4961C33.0425 10.7515 33.7443 12.9114 32.4725 14.1511L26.8778 19.6046C26.3728 20.0969 26.1423 20.8062 26.2616 21.5013L27.5823 29.2017C27.8825 30.9522 26.0452 32.2871 24.4731 31.4607L17.5577 27.825C16.9334 27.4968 16.1877 27.4968 15.5634 27.825L8.648 31.4607C7.07594 32.2871 5.23858 30.9522 5.53882 29.2017L6.85954 21.5013C6.97877 20.8062 6.7483 20.0969 6.24326 19.6046L0.648594 14.1511C-0.623228 12.9114 0.0785799 10.7515 1.83619 10.4961L9.56784 9.37261C10.2658 9.27119 10.8691 8.83283 11.1813 8.20038L14.639 1.19432Z" fill="#FED200" />
                  </svg>
                </div>
                {isVisualFixture ? (
                  <div data-layer="4.1" style={{ height: 34, justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'black', fontSize: 28, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 700, lineHeight: '34px' }}>4.1</div>
                ) : (filmDetailVm?.communityRatingAverage != null && filmDetailVm.communityRatingAverage > 0) ? (
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                    <span style={{ color: 'black', fontSize: 28, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 700, lineHeight: '34px' }}>
                      {filmDetailVm.communityRatingAverage.toFixed(1)}
                    </span>
                    <span style={{ color: '#898992', fontSize: 14, fontFamily: 'Pretendard' }}>
                      ({filmDetailVm.communityRatingCount || 0})
                    </span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                    <span style={{ color: 'black', fontSize: 28, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 700, lineHeight: '34px' }}>—</span>
                    <span style={{ color: '#898992', fontSize: 13, fontFamily: 'Pretendard' }}>No ratings yet</span>
                  </div>
                )}
              </div>
            </div>
            <div data-testid="film-detail-external-ratings" data-layer="Frame 2147227252" style={{ height: 21, justifyContent: 'flex-start', alignItems: 'center', gap: 16, display: 'flex' }}>
              {isVisualFixture ? (
                <>
                  <div data-layer="🍅 50%" style={{ textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 400, lineHeight: '21.5px' }}>🍅 50%</div>
                  <div data-layer="🍿 50%" style={{ textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 400, lineHeight: '21.5px' }}>🍿 50%</div>
                  <div data-layer="IMDb: 50%" style={{ textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard, -apple-system, sans-serif', fontWeight: 400, lineHeight: '21.5px' }}>IMDb: 50%</div>
                </>
              ) : null}
            </div>
          </div>

          {/* Section: Director / Cast Composite (Carryover 004B) */}
          <div
            data-testid="film-detail-cast-composite"
            style={{
              position: 'relative',
              width: 1920,
              height: 487,
              overflow: 'visible',
            }}
          >
            {/* Base background tail: preserves base 553:7723 background through Y=1349 */}
            <div
              data-testid="film-detail-cast-background-tail"
              aria-hidden="true"
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                width: 1920,
                height: 507,
                background: 'var(--Gray-50, #F8F8FA)',
                borderBottom: '1px var(--Gray-100, #F2F2F5) solid',
                boxSizing: 'border-box',
              }}
            />

            {/* Top Cast Layer (553:7972) */}
            <div
              data-testid="film-detail-director-cast"
              data-layer="Frame 2147227275"
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                width: 1920,
                height: 487,
                boxSizing: 'border-box',
                paddingLeft: 120,
                paddingRight: 120,
                paddingTop: 40,
                paddingBottom: 40,
                background: 'var(--Gray-50, #F8F8FA)',
                borderBottom: '1px var(--Gray-100, #F2F2F5) solid',
                flexDirection: 'column',
                justifyContent: 'flex-start',
                alignItems: 'flex-start',
                gap: 24,
                display: 'flex',
              }}
            >
              <div
                data-testid="film-detail-cast-heading"
                data-layer="Director / Cast"
                style={{
                  width: 1680,
                  height: 24,
                  justifyContent: 'center',
                  display: 'flex',
                  flexDirection: 'column',
                  color: '#4A4A53',
                  fontSize: 20,
                  fontFamily: 'Pretendard, -apple-system, sans-serif',
                  fontWeight: 600,
                  lineHeight: 'normal',
                }}
              >
                Director / Cast
              </div>
              <div
                data-testid="film-detail-cast-row"
                data-layer="Frame 2147227256"
                style={{
                  width: 1680,
                  height: 358,
                  justifyContent: 'flex-start',
                  alignItems: 'center',
                  gap: 16,
                  display: 'flex',
                }}
              >
                {(() => {
                  const castList = isVisualFixtureMode()
                    ? FIGMA_CAST_MEMBERS
                    : (filmDetailVm?.cast && filmDetailVm.cast.length > 0
                        ? filmDetailVm.cast.map((member: any) => {
                            const normalizedName = (member.name || '').trim().toLowerCase();
                            const matched = FIGMA_CAST_MEMBERS.find(f => f.name.toLowerCase() === normalizedName
                              || (normalizedName === 'dewitt clarke jennings' && f.name === 'DeWitt Jennings'));
                            const image = member.image || matched?.image || null;
                            return {
                              id: member.id,
                              name: member.name || 'Cast Member',
                              role: member.role || matched?.role || 'Cast',
                              image: image,
                              imageSource: member.imageSource,
                              imagePosition: member.imagePosition,
                              alt: member.alt || `Portrait of ${member.name || 'Cast Member'}`,
                              isPlaceholder: !image,
                            };
                          })
                        : []);
                  if (!isVisualFixtureMode() && castList.length === 0) {
                    return (
                      <div
                        data-testid="film-detail-cast-empty"
                        style={{
                          color: '#898992',
                          fontSize: 16,
                          fontFamily: 'Pretendard, -apple-system, sans-serif',
                          padding: '24px 0',
                        }}
                      >
                        No cast information available.
                      </div>
                    );
                  }
                  return castList.map((member: any, idx: number) => (
                    <div
                      key={idx}
                      data-testid={`film-detail-cast-card-${idx}`}
                      data-layer={member.id ? `Frame ${member.id}` : `card-${idx}`}
                      style={{
                        width: 220,
                        height: 358,
                        flexShrink: 0,
                        flexDirection: 'column',
                        justifyContent: 'flex-start',
                        alignItems: 'flex-start',
                        gap: 16,
                        display: 'flex',
                        boxSizing: 'border-box',
                      }}
                    >
                      <div
                        data-testid={`film-detail-cast-image-${idx}`}
                        style={{
                          width: 220,
                          height: 300,
                          borderRadius: 20,
                          overflow: 'hidden',
                          flexShrink: 0,
                          position: 'relative',
                        }}
                      >
                        {member.image ? (
                          <img
                            src={member.image}
                            alt={member.alt || `Portrait of ${member.name}`}
                            style={{
                              width: 220,
                              height: 300,
                              objectFit: 'cover',
                              objectPosition: member.imagePosition || 'center',
                              display: 'block',
                            }}
                          />
                        ) : (
                          <div
                            role="img"
                            aria-label={member.alt || `Portrait of ${member.name}`}
                            style={{
                              width: 220,
                              height: 300,
                              background: '#E6E6EA',
                              borderRadius: 20,
                              display: 'flex',
                              flexDirection: 'column',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: '#898992',
                              fontSize: 14,
                              fontFamily: 'Pretendard, -apple-system, sans-serif',
                              textAlign: 'center',
                              padding: '12px',
                              boxSizing: 'border-box',
                            }}
                          >
                            Photo unavailable
                          </div>
                        )}
                        {member.image && member.imageSource && (
                          <a href={member.imageSource} target="_blank" rel="noopener noreferrer"
                            aria-label={`Photo source for ${member.name}`}
                            style={{ position: 'absolute', bottom: 8, right: 8, padding: '5px 8px', borderRadius: 6, background: 'rgba(0,0,0,.7)', color: '#fff', fontSize: 11 }}>
                            Photo source ↗
                          </a>
                        )}
                      </div>
                    <div
                      style={{
                        width: 220,
                        height: 42,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 4,
                      }}
                    >
                      <div
                        data-testid={`film-detail-cast-name-${idx}`}
                        data-layer={member.name}
                        style={{
                          width: 220,
                          height: 21,
                          textAlign: 'center',
                          justifyContent: 'center',
                          display: 'flex',
                          flexDirection: 'column',
                          color: '#000000',
                          fontSize: 18,
                          fontFamily: 'Pretendard, -apple-system, sans-serif',
                          fontWeight: 600,
                          lineHeight: 'normal',
                          overflow: 'hidden',
                        }}
                      >
                        {member.name}
                      </div>
                      <div
                        data-testid={`film-detail-cast-role-${idx}`}
                        data-layer={member.role}
                        style={{
                          width: 220,
                          height: 17,
                          textAlign: 'center',
                          justifyContent: 'center',
                          display: 'flex',
                          flexDirection: 'column',
                          color: '#4A4A53',
                          fontSize: 14,
                          fontFamily: 'Pretendard, -apple-system, sans-serif',
                          fontWeight: 400,
                          lineHeight: 'normal',
                          overflow: 'hidden',
                        }}
                      >
                        {member.role}
                      </div>
                    </div>
                  </div>
                ));
                })()}
              </div>
            </div>
          </div>

          {/* Section: Critic Reviews Composite (D03: no hidden, single heading) */}
          <div
            data-testid="film-detail-critic-reviews"
            data-layer="Frame 2147227283"
            style={{
              position: 'relative',
              width: 1920,
              minHeight: 180,
              overflow: 'visible',
              background: '#FFFFFF',
              boxSizing: 'border-box',
              padding: '40px 120px',
            }}
          >
            {/* Top Heading */}
            <div
              data-testid="film-detail-critic-heading-top"
              data-layer="Frame 2147227205"
              style={{
                width: 1680,
                height: 24,
                marginBottom: 24,
                display: 'flex',
                alignItems: 'center',
                color: '#4A4A53',
                fontSize: 20,
                fontFamily: 'Pretendard, -apple-system, sans-serif',
                fontWeight: 600,
                lineHeight: 'normal',
                zIndex: 2,
              }}
            >
              Critic Reviews
            </div>

            {!isVisualFixture ? (
              <div
                data-testid="critic-reviews-empty"
                style={{
                  color: '#898992',
                  fontSize: 16,
                  fontFamily: 'Pretendard, -apple-system, sans-serif',
                  padding: '24px 0',
                }}
              >
                No verified critic reviews are available.
              </div>
            ) : (
              <>

            {/* Base Card-Background Row (553:7757, global Y=1437, aria-hidden) */}
            <div
              data-testid="film-detail-critic-base-row"
              data-layer="Frame 2147227282"
              aria-hidden="true"
              style={{
                position: 'absolute',
                left: 120,
                top: 108,
                width: 1680,
                height: 232,
                display: 'flex',
                alignItems: 'center',
                gap: 20,
                zIndex: 1,
              }}
            >
              <div
                data-testid="film-detail-critic-base-background-0"
                style={{
                  width: 'calc((100% - 40px) / 3)',
                  height: 232,
                  background: '#F8F8FA',
                  borderRadius: 20,
                  flexShrink: 0,
                  boxSizing: 'border-box',
                }}
              />
              <div
                data-testid="film-detail-critic-base-background-1"
                style={{
                  width: 'calc((100% - 40px) / 3)',
                  height: 232,
                  background: '#F8F8FA',
                  borderRadius: 20,
                  flexShrink: 0,
                  boxSizing: 'border-box',
                }}
              />
              <div
                data-testid="film-detail-critic-base-background-2"
                style={{
                  width: 'calc((100% - 40px) / 3)',
                  height: 211,
                  background: '#F8F8FA',
                  borderRadius: 20,
                  flexShrink: 0,
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Top Visible Card Row (553:8006, global Y=1417) */}
            <div
              data-testid="film-detail-critic-row"
              data-layer="Frame 2147227282"
              style={{
                position: 'absolute',
                left: 120,
                top: 88,
                width: 1680,
                height: 232,
                display: 'flex',
                alignItems: 'center',
                gap: 20,
                zIndex: 2,
              }}
            >
              {(isVisualFixtureMode() ? FIGMA_CRITIC_REVIEWS : (Array.isArray(filmDetail?.critic_reviews) ? filmDetail.critic_reviews : [])).slice(0, 3).map((review: any, idx: number) => {
                const isCard2 = idx === 2;
                const cardHeight = isCard2 ? 211 : 232;
                return (
                  <div
                    key={review.id || idx}
                    data-testid={`film-detail-critic-card-${idx}`}
                    data-layer={review.id ? `Frame ${review.id}` : `card-${idx}`}
                    style={{
                      width: 'calc((100% - 40px) / 3)',
                      height: cardHeight,
                      background: '#F8F8FA',
                      borderRadius: 20,
                      paddingLeft: 40,
                      paddingRight: 244,
                      paddingTop: 40,
                      paddingBottom: 40,
                      boxSizing: 'border-box',
                      overflow: 'visible',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'flex-start',
                      alignItems: 'flex-start',
                      flexShrink: 0,
                    }}
                  >
                    <div
                      data-layer="Frame 2147227277"
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 36,
                        width: 332.2857,
                        flexShrink: 0,
                      }}
                    >
                      <div
                        role="img"
                        aria-label="Critic avatar placeholder"
                        data-testid={`film-detail-critic-avatar-${idx}`}
                        style={{ width: 70, height: 70, flexShrink: 0 }}
                      >
                        <img
                          src="/assets/figma-current/film-detail/critic-reviews/avatar-placeholder.svg"
                          alt=""
                          style={{ width: 70, height: 70, display: 'block' }}
                        />
                      </div>
                      <div
                        data-layer="Frame 2147227276"
                        style={{
                          width: 226.2857,
                          paddingTop: 12,
                          display: 'flex',
                          flexDirection: 'column',
                          gap: 20,
                          flexShrink: 0,
                        }}
                      >
                        <div
                          data-testid={`film-detail-critic-rating-${idx}`}
                          data-layer="Frame 2147227207"
                          style={{
                            width: 139,
                            height: 24,
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: 8,
                          }}
                        >
                          <div
                            data-layer="Frame 2147227208"
                            style={{ width: 120, height: 24, flexShrink: 0 }}
                          >
                            <img
                              src="/assets/figma-current/film-detail/critic-reviews/stars-4-of-5.svg"
                              alt=""
                              style={{ width: 120, height: 24, display: 'block' }}
                            />
                          </div>
                          <div
                            data-layer="4"
                            style={{
                              width: 11,
                              height: 19,
                              marginTop: 2.5,
                              display: 'flex',
                              flexDirection: 'column',
                              justifyContent: 'center',
                              color: '#AFAFB8',
                              fontSize: 16,
                              fontFamily: 'Pretendard, -apple-system, sans-serif',
                              fontWeight: 500,
                              lineHeight: 'normal',
                            }}
                          >
                            {review.score}
                          </div>
                        </div>
                        <div
                          data-testid={`film-detail-critic-body-${idx}`}
                          data-layer="Frame 2147227279"
                          style={{
                            width: 226.2857,
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 12,
                          }}
                        >
                          <div
                            data-testid={`film-detail-critic-identity-${idx}`}
                            data-layer="Frame 2147227278"
                            style={{
                              height: 21,
                              display: 'flex',
                              alignItems: 'center',
                              gap: 16,
                              overflow: 'visible',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            <div
                              data-layer={review.reviewer}
                              style={{
                                color: '#4A4A53',
                                fontSize: 18,
                                fontFamily: 'Pretendard, -apple-system, sans-serif',
                                fontWeight: 600,
                                lineHeight: 'normal',
                              }}
                            >
                              {review.reviewer}
                            </div>
                            <div
                              data-layer={review.date}
                              style={{
                                height: 14,
                                color: '#898992',
                                fontSize: 12,
                                fontFamily: 'Pretendard, -apple-system, sans-serif',
                                fontWeight: 300,
                                lineHeight: 'normal',
                              }}
                            >
                              {review.date}
                            </div>
                          </div>
                          <div
                            data-layer="quote"
                            style={{
                              width: 226.2857,
                              color: '#6B6B75',
                              fontSize: 14,
                              fontFamily: 'Pretendard, -apple-system, sans-serif',
                              fontWeight: 400,
                              lineHeight: '21px',
                            }}
                          >
                            {review.quote}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            </>
            )}
          </div>

          {/* Section: Reframe (1:1 Figma 553:8058) */}
          <section
            data-layer="Frame 2147227196"
            data-testid="film-detail-reframe"
            style={{
              width: 1920,
              height: 757,
              boxSizing: 'border-box',
              background: '#F8F8FA',
              padding: '50px 120px',
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              alignItems: 'flex-start',
              justifyContent: 'flex-start',
            }}
          >
            {/* Header & Timeline Group (553:8059) */}
            <div
              data-layer="Frame 2147227313"
              style={{
                width: 1680,
                height: 109,
                display: 'flex',
                flexDirection: 'column',
                gap: 24,
                boxSizing: 'border-box',
              }}
            >
              {/* Header row (553:8060) */}
              <div
                data-layer="Frame 2147227205"
                data-testid="film-detail-reframe-header"
                style={{
                  width: 1680,
                  height: 24,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  boxSizing: 'border-box',
                }}
              >
                <div
                  data-layer="Reframe"
                  data-testid="film-detail-reframe-title"
                  style={{
                    width: 78,
                    height: 24,
                    display: 'flex',
                    alignItems: 'center',
                    color: '#4A4A53',
                    fontSize: 20,
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                    fontWeight: 600,
                    lineHeight: '24px',
                  }}
                >
                  Reframe
                </div>
                <div
                  data-layer="Full Runtime 00:00:00"
                  data-testid="film-detail-reframe-runtime"
                  style={{
                    height: 19,
                    display: 'flex',
                    alignItems: 'center',
                    color: '#898992',
                    fontSize: 16,
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                    fontWeight: 400,
                    lineHeight: 'normal',
                  }}
                >
                  {isVisualFixture
                    ? 'Total Runtime 00:00:00'
                    : (filmDetailVm?.durationMins ? `Total Runtime ${filmDetailVm.durationMins}m` : (filmDetailVm?.runtimeDisplay ? `Total Runtime ${filmDetailVm.runtimeDisplay}` : 'Total Runtime 00:00:00'))}
                </div>
              </div>

              {/* Timeline group (553:8063) */}
              <div
                data-layer="Frame 2147227312"
                data-testid="film-detail-reframe-timeline"
                style={{
                  width: isVisualFixture ? 1680 : '100%',
                  maxWidth: 1680,
                  height: isVisualFixture ? 61 : 'auto',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                  boxSizing: 'border-box',
                }}
              >
                {!isVisualFixture && filmDetailVm && (
                  <FilmJourneyControls
                    key={`${filmDetailVm.movieId}:${filmDetailVm.editionId || 'default'}:${progressRevision}`}
                    movieId={filmDetailVm.movieId}
                    editionId={filmDetailVm.editionId || filmDetail?.edition_id || ''}
                    runtimeMs={filmDetailVm.runtimeMs || filmDetail?.runtime_ms || ((filmDetailVm.durationMins || 0) * 60000)}
                    reveals={revealsVm}
                    initialProgressMs={previewProgressMs ?? (filmDetail?.viewer_progress_ms || 0)}
                    onProgressChange={() => {
                      if (activeMovieIdRef.current !== filmDetailVm.movieId) return;
                      retryFilm();
                      retryReveals();
                    }}
                    onProgressPreview={(ms) => {
                      if (ms !== (previewProgressMs ?? (filmDetail?.viewer_progress_ms || 0))) closeAnalysis();
                      userEditedProgressRef.current = true;
                      setPreviewProgressMs(ms);
                    }}
                    onSavingChange={setProgressSaving}
                  >
                    {showAnalysis && watchedReveals.length > 0 && <RevealTimelineMarkers reveals={watchedReveals}
                      runtimeMs={filmDetailVm.runtimeMs || 0} selectedId={selectedRevealId}
                      onSelect={reveal => {
                        pendingTimelineScroll.current = true;
                        setSelectedRevealId(reveal.revealId);
                        activeRevealIdRef.current = reveal.revealId;
                        setActiveCardIndex(0);
                        loadProofsForReveal(filmDetailVm.movieId, reveal.revealId, ++proofsReqIdRef.current);
                      }} />}
                  </FilmJourneyControls>
                )}
                {/* Marker Row (553:8064) */}
                {isVisualFixture &&
                <div
                  data-layer="Frame 2147227310"
                  data-testid="film-detail-reframe-marker-row"
                  style={{
                    position: 'relative',
                    width: isVisualFixture ? 1680 : '100%',
                    maxWidth: 1680,
                    height: isVisualFixture ? 20 : Math.max(44, revealsVm.length * 44),
                    paddingLeft: 20,
                    paddingRight: 20,
                    boxSizing: 'border-box',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  {isVisualFixture && TIMELINE_MARKERS.map((markerSrc, idx) => (
                    <img key={idx} src={markerSrc} alt="" style={{ width: 59, height: 20 }} />
                  ))}
                </div>}

                {/* Progress Bar (553:8087) */}
                {isVisualFixture && (() => {
                  const timelineRuntimeMs = filmDetail?.runtime_ms || (filmDetailVm?.durationMins ? filmDetailVm.durationMins * 60000 : 5119000);
                  const viewerProgressMs = filmDetail?.viewer_progress_ms ?? 0;
                  const progressRatio = Math.min(1, Math.max(0, timelineRuntimeMs > 0 ? (viewerProgressMs / timelineRuntimeMs) : 0));
                  const activeBarWidth = Math.round(1680 * progressRatio);
                  const inactiveBarWidth = 1680 - activeBarWidth;
                  const formatTimeTick = (ms: number) => {
                    const s = Math.floor(ms / 1000);
                    const h = Math.floor(s / 3600);
                    const m = Math.floor((s % 3600) / 60);
                    const sec = s % 60;
                    const pad = (n: number) => n.toString().padStart(2, '0');
                    return `${pad(h)}:${pad(m)}:${pad(sec)}`;
                  };

                  return (
                    <>
                      <div
                        data-layer="Frame 2147227308"
                        style={{
                          width: isVisualFixture ? 1680 : '100%',
                          maxWidth: 1680,
                          height: 8,
                          display: 'flex',
                          boxSizing: 'border-box',
                        }}
                      >
                        <div
                          data-layer="Rectangle 240655233"
                          data-testid="film-detail-reframe-progress-active"
                          style={{
                            width: isVisualFixture ? 524 : `${(progressRatio * 100).toFixed(2)}%`,
                            height: 8,
                            background: '#4C22F4',
                            flexShrink: 0,
                          }}
                        />
                        <div
                          data-layer="Rectangle 240655234"
                          data-testid="film-detail-reframe-progress-inactive"
                          style={{
                            width: isVisualFixture ? 1156 : `${((1 - progressRatio) * 100).toFixed(2)}%`,
                            height: 8,
                            background: '#E6E6EA',
                            flexShrink: 0,
                          }}
                        />
                      </div>

                      {/* Timestamp Row (553:8090) */}
                      <div
                        data-layer="Frame 2147227311"
                        data-testid="film-detail-reframe-timestamp-row"
                        style={{
                          width: isVisualFixture ? 1680 : '100%',
                          maxWidth: 1680,
                          height: 17,
                          paddingLeft: 16,
                          paddingRight: 16,
                          boxSizing: 'border-box',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                        }}
                      >
                        {(isVisualFixture ? [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] : [0, 10]).map((idx) => {
                          const tickMs = Math.round((idx / 10) * timelineRuntimeMs);
                          const tickLabel = isVisualFixture ? "00:00:00" : formatTimeTick(tickMs);
                          const isTickActive = isVisualFixture ? idx === 3 : (viewerProgressMs > 0 && Math.abs(tickMs - viewerProgressMs) < (timelineRuntimeMs / 10));
                          return (
                            <div
                              key={idx}
                              data-layer={tickLabel}
                              style={{
                                color: isTickActive ? '#4C22F4' : '#898992',
                                fontSize: 14,
                                fontFamily: 'Pretendard, -apple-system, sans-serif',
                                fontWeight: isTickActive ? 600 : 400,
                                lineHeight: '17px',
                                display: 'flex',
                                justifyContent: 'center',
                              }}
                            >
                              {tickLabel}
                            </div>
                          );
                        })}
                      </div>
                    </>
                  );
                })()}
              </div>
            </div>

            {/* Card Grid (553:8102, D04 repeat(2, minmax(0, 1fr))) */}
            {!isVisualFixture && separatedAnalysis && filmDetailVm && filmDetailVm.movieId === movieId && <SelectedPortionAnalysis
              movieId={filmDetailVm.movieId} editionId={filmDetailVm.editionId || ''} positionMs={safeProgress}
              disabled={filmLoading || progressSaving || authLoading}
              viewerKey={user?.id || 'guest'} />}
            {!isVisualFixture && separatedAnalysis && <h2 className="reinterpretation-heading">Post-reveal reinterpretation</h2>}
            {!isVisualFixture && <div className="watched-analysis-actions">
              <button type="button" className="watched-analysis-toggle" data-testid="watched-analysis-toggle"
                aria-expanded={showAnalysis} aria-controls="watched-analysis-content"
                disabled={filmLoading || progressSaving || !filmDetailVm ||
                  (separatedAnalysis && safeProgress < (filmDetailVm.runtimeMs || Infinity))}
                onClick={() => {
                  if (showAnalysis) { closeAnalysis(); return; }
                  analysisProgress.current = safeProgress;
                  analysisOwner.current = `${movieId}:${editionId || ''}`;
                  analysisOpenRef.current = true;
                  setAnalysisOpen(true);
                  loadReveals(movieId || '', ++revealsReqIdRef.current);
                }}>
                {separatedAnalysis ? (showAnalysis ? 'Hide reinterpretation' : 'Show post-reveal reinterpretation') :
                  showAnalysis ? 'Hide analysis' : (filmDetailVm?.runtimeMs && safeProgress >= filmDetailVm.runtimeMs ? 'Show full-film analysis' : 'Show watched-part analysis')}
              </button>
              {!showAnalysis && <p>{separatedAnalysis ? 'These readings use full-film context. Finish this edition, then open them separately.' :
                'Analysis stays hidden until you choose to open it.'}</p>}
            </div>}
            {(isVisualFixture || showAnalysis) && <div
              id="watched-analysis-content"
              data-layer="Frame 2147227190"
              data-testid="film-detail-reframe-grid"
              style={{
                width: isVisualFixture ? 1680 : '100%',
                maxWidth: 1680,
                minHeight: isVisualFixture ? 532 : 0,
                display: 'grid',
                gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                columnGap: '20px',
                rowGap: '20px',
                boxSizing: 'border-box',
              }}
            >
              {!isVisualFixture && filmDetailVm?.coreDemoSupported === false ? (
                <div data-testid="unsupported-analysis-notice" style={{ gridColumn: 'span 2', padding: '36px 40px', background: '#FFFFFF', borderRadius: 12, border: '1px solid #E6E6EA', display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ color: '#2D2D34', fontSize: 20, fontFamily: 'Pretendard', fontWeight: 600 }}>
                    {filmDetailVm?.analysisStatus === 'PREPARING' ? 'Analysis Preparing' : 'Analysis Not Available'}
                  </div>
                  <div style={{ color: '#6B6B75', fontSize: 16, fontFamily: 'Pretendard', lineHeight: '24px' }}>
                    {filmDetailVm?.notice || 'Analysis has not been published for this edition.'}
                  </div>
                  <div style={{ color: '#898992', fontSize: 14, fontFamily: 'Pretendard' }}>
                    Selected film: {filmDetailVm?.title || 'Unknown'}
                  </div>
                </div>
              ) : !isVisualFixture && revealsError ? (
                <div style={{ gridColumn: 'span 2' }}>
                  <ErrorState
                    title="Failed to Load Reveals"
                    message={revealsError.message || 'Unable to retrieve reveals.'}
                    statusCode={revealsError.status}
                    onRetry={retryReveals}
                  />
                </div>
              ) : !isVisualFixture && revealsLoading ? (
                <div style={{ gridColumn: 'span 2' }}>
                  <LoadingState message="Investigating narrative memory..." />
                </div>
              ) : !isVisualFixture && watchedReveals.length === 0 ? (
                <div style={{ gridColumn: 'span 2' }}>
                  <EmptyState
                    title="No analysis available for your watched portion"
                    message="Your viewing position is saved. You can close this panel and keep watching."
                  />
                </div>
              ) : !isVisualFixture && proofsError ? (
                <div style={{ gridColumn: 'span 2' }}>
                  <ErrorState
                    title="Failed to Load Proofs"
                    message={proofsError.message || 'Unable to retrieve proof records.'}
                    statusCode={proofsError.status}
                    onRetry={retryProofs}
                  />
                </div>
              ) : !isVisualFixture && proofsLoading ? (
                <div style={{ gridColumn: 'span 2' }}>
                  <LoadingState message="Investigating narrative memory..." />
                </div>
              ) : !isVisualFixture && reframeCards.length === 0 ? (
                <div style={{ gridColumn: 'span 2' }}>
                  <EmptyState
                    title="No Interpretations for This Reveal Yet"
                    message="Choose another reveal to explore available analyses. AI interpretations are labelled separately from verified evidence."
                  />
                </div>
              ) : (
                reframeCards.map((card, cardIdx) => {
                  if (!isVisualFixture) return <WatchedAnalysisCard key={card.id} card={card} index={cardIdx} navigate={navigate} />;
                  const effectiveProgress = previewProgressMs ?? (filmDetail?.viewer_progress_ms ?? 0);
                  const validCutoffMs = (typeof card.spoilerCutoffMs === 'number' && Number.isFinite(card.spoilerCutoffMs) && card.spoilerCutoffMs >= 0)
                    ? card.spoilerCutoffMs
                    : null;
                  const isCardSpoilerLocked = Boolean(
                    card.isLocked ||
                    effectiveProgress === 0 ||
                    validCutoffMs === null ||
                    effectiveProgress < validCutoffMs
                  );
                  const isSpoilerHidden = isVisualFixture
                    ? Boolean(card.hasSpoiler && !revealedSpoilers[card.id])
                    : isCardSpoilerLocked;
                  return (
                    <div
                      key={card.id || cardIdx}
                      className={isSpoilerHidden ? 'film-detail-card-masked' : undefined}
                      data-layer={`Frame 2147227${cardIdx === 0 ? '187' : cardIdx === 1 ? '307' : cardIdx === 2 ? '308' : '309'}`}
                      data-testid={`film-detail-reframe-card-${cardIdx}`}
                      onClick={() => {
                        if (isSpoilerHidden) return;
                        setActiveCardIndex(cardIdx);
                      }}
                      style={{
                        width: '100%',
                        minWidth: 0,
                        minHeight: 256,
                        background: '#FFFFFF',
                        borderRadius: 12,
                        padding: '32px 30px',
                        boxSizing: 'border-box',
                        position: 'relative',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'flex-start',
                        alignItems: 'flex-start',
                        cursor: 'pointer',
                        border: activeCardIndex === cardIdx ? '2px solid var(--Purple-500, #4C22F4)' : '1px solid transparent',
                        boxShadow: activeCardIndex === cardIdx ? '0 0 16px rgba(76, 34, 244, 0.25)' : 'none',
                        transition: 'border 0.2s ease, box-shadow 0.2s ease',
                      }}
                    >
                      {/* Top Row: Scene, Time badge, More button */}
                      <div
                        data-layer="Frame 2147227297"
                        style={{
                          width: '100%',
                          minWidth: 0,
                          height: 25,
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          boxSizing: 'border-box',
                        }}
                      >
                        <div
                          data-layer="Frame 2147227302"
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            height: 25,
                          }}
                        >
                          <div
                            data-layer="SCENE 1"
                            data-testid={`film-detail-reframe-scene-${cardIdx}`}
                            style={{
                              color: '#4C22F4',
                              fontSize: 16,
                              fontFamily: 'Pretendard, -apple-system, sans-serif',
                              fontWeight: 500,
                              lineHeight: 'normal',
                            }}
                          >
                            {card.scene}
                          </div>
                          {!isSpoilerHidden && card.timestamp && (
                            <div
                              data-layer="Frame 2147227309"
                              data-testid={`film-detail-reframe-time-${cardIdx}`}
                              style={{
                                height: 25,
                                padding: 4,
                                boxSizing: 'border-box',
                                background: '#F1F0FF',
                                borderRadius: 4,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: '#B7B3FF',
                                fontSize: 14,
                                fontFamily: 'Pretendard, -apple-system, sans-serif',
                                fontWeight: 400,
                                lineHeight: 'normal',
                              }}
                            >
                              {card.timestamp}
                            </div>
                          )}
                        </div>

                        <button
                          type="button"
                          data-layer="Frame 2147227206"
                          data-testid={`film-detail-reframe-more-${cardIdx}`}
                          disabled={isSpoilerHidden}
                          aria-disabled={isSpoilerHidden ? true : undefined}
                          aria-label={isSpoilerHidden ? 'More' : `More details for ${card.title}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (isSpoilerHidden) return;
                            if (isVisualFixture) {
                              setSelectedReframeModalMoment({
                                id: card.id,
                                scene: card.scene,
                                timestamp: card.timestamp,
                                title: card.title,
                                interpretation: card.body,
                              });
                            } else {
                              if (card.id) {
                                navigate(`/proofs/${encodeURIComponent(card.id)}`);
                              }
                            }
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.stopPropagation();
                              if (isSpoilerHidden) return;
                              if (isVisualFixture) {
                                setSelectedReframeModalMoment({
                                  id: card.id,
                                  scene: card.scene,
                                  timestamp: card.timestamp,
                                  title: card.title,
                                  interpretation: card.body,
                                });
                              } else {
                                if (card.id) {
                                  navigate(`/proofs/${encodeURIComponent(card.id)}`);
                                }
                              }
                            }
                          }}
                          style={{
                            width: 57,
                            height: 20,
                            background: 'transparent',
                            border: 'none',
                            padding: 0,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 4,
                            cursor: isSpoilerHidden ? 'default' : 'pointer',
                          }}
                        >
                          <span
                            data-layer="More"
                            style={{
                              color: '#898992',
                              fontSize: 14,
                              fontFamily: 'Pretendard, -apple-system, sans-serif',
                              fontWeight: 400,
                              lineHeight: '20px',
                            }}
                          >
                            More
                          </span>
                          <img
                            src="/assets/figma-current/film-detail/reframe/chevron-right.svg"
                            alt=""
                            aria-hidden="true"
                            style={{ width: 20, height: 20, display: 'block' }}
                          />
                        </button>
                      </div>

                      {/* Content Block: Title + Body */}
                      <div
                        id={`film-detail-reframe-content-${cardIdx}`}
                        data-layer="Frame 2147227305"
                        aria-hidden={isVisualFixture && isSpoilerHidden ? true : undefined}
                        style={{
                          width: '100%',
                          minWidth: 0,
                          marginTop: 8,
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'flex-start',
                          boxSizing: 'border-box',
                        }}
                      >
                        <div
                          data-layer="Title"
                          data-testid={`film-detail-reframe-title-${cardIdx}`}
                          style={{
                            width: '100%',
                            minWidth: 0,
                            color: '#2D2D34',
                            fontSize: 18,
                            fontFamily: 'Pretendard, -apple-system, sans-serif',
                            fontWeight: 600,
                            lineHeight: 'normal',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {isSpoilerHidden ? 'Spoiler Protected Scene' : card.title}
                        </div>
                        <div
                          data-layer="Body"
                          data-testid={`film-detail-reframe-body-${cardIdx}`}
                          style={{
                            width: '100%',
                            minWidth: 0,
                            height: 'auto',
                            maxHeight: 63,
                            marginTop: 15,
                            marginBottom: 16,
                            color: '#898992',
                            fontSize: 14,
                            fontFamily: 'Pretendard, -apple-system, sans-serif',
                            fontWeight: 400,
                            lineHeight: '21px',
                            overflow: 'hidden',
                            display: '-webkit-box',
                            WebkitLineClamp: 3,
                            WebkitBoxOrient: 'vertical',
                          }}
                        >
                          {isSpoilerHidden ? 'This scene contains spoilers beyond your current viewing progress. Move the viewing progress timeline forward to reveal this scene.' : card.body}
                        </div>
                      </div>

                      {/* Counter Row: Like & Comment (D04: normal flow with margin-top auto) */}
                      <div
                        data-layer="Frame 2147227304"
                        style={{
                          width: '100%',
                          minWidth: 0,
                          marginTop: 'auto',
                          height: 32,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 12,
                          boxSizing: 'border-box',
                        }}
                      >
                        <div
                          data-layer="LikeButton"
                          data-testid={`film-detail-reframe-like-${cardIdx}`}
                          style={{
                            width: 65,
                            height: 32,
                            padding: 6,
                            borderRadius: 8,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            boxSizing: 'border-box',
                          }}
                        >
                          <img
                            src="/assets/figma-current/film-detail/reframe/heart.svg"
                            alt=""
                            aria-hidden="true"
                            style={{ width: 20, height: 20, display: 'block' }}
                          />
                          <span
                            data-layer="Like Count"
                            style={{
                              color: '#AFAFB8',
                              fontSize: 14,
                              fontFamily: 'Pretendard, -apple-system, sans-serif',
                              fontWeight: 600,
                              lineHeight: 'normal',
                            }}
                          >
                            {card.likes != null ? card.likes : '—'}
                          </span>
                        </div>

                        <div
                          data-layer="CountItem"
                          data-testid={`film-detail-reframe-comment-${cardIdx}`}
                          style={{
                            width: 54,
                            height: 32,
                            padding: 6,
                            borderRadius: 8,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            boxSizing: 'border-box',
                          }}
                        >
                          <img
                            src="/assets/figma-current/film-detail/reframe/comment.svg"
                            alt=""
                            aria-hidden="true"
                            style={{ width: 20, height: 20, display: 'block' }}
                          />
                          <span
                            data-layer="Like Count"
                            style={{
                              color: '#AFAFB8',
                              fontSize: 14,
                              fontFamily: 'Pretendard, -apple-system, sans-serif',
                              fontWeight: 600,
                              lineHeight: 'normal',
                            }}
                          >
                            {card.comments != null ? card.comments : '—'}
                          </span>
                        </div>
                      </div>

                      {/* Spoiler Overlay (shown whenever content is spoiler hidden) */}
                      {isSpoilerHidden && (
                        <div
                          data-testid="film-detail-reframe-spoiler-overlay"
                          style={{
                            position: 'absolute',
                            left: 0,
                            top: 65,
                            width: '100%',
                            maxWidth: 830,
                            height: 127,
                            background: 'linear-gradient(180deg, rgba(255, 255, 255, 0) 0%, rgba(255, 255, 255, 0.95) 30%, #FFFFFF 100%)',
                            borderRadius: '0 0 12px 12px',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'flex-start',
                            paddingTop: 36,
                            boxSizing: 'border-box',
                            zIndex: 2,
                          }}
                        >
                          <div
                            data-layer="Frame 2147227306"
                            style={{
                              width: '100%',
                              maxWidth: 320,
                              height: 71,
                              display: 'flex',
                              flexDirection: 'column',
                              alignItems: 'center',
                              gap: 12,
                              boxSizing: 'border-box',
                            }}
                          >
                            <div
                              data-layer="This content contains spoilers."
                              style={{
                                width: '100%',
                                height: 21,
                                color: '#898992',
                                fontSize: 14,
                                fontFamily: 'Pretendard, -apple-system, sans-serif',
                                fontWeight: 400,
                                lineHeight: '21px',
                                textAlign: 'center',
                              }}
                            >
                              This content contains spoilers.
                            </div>
                            {(
                              <button
                                type="button"
                                data-layer="AppButton"
                                data-testid="film-detail-reframe-reveal-button"
                                aria-controls={`film-detail-reframe-content-${cardIdx}`}
                                aria-expanded={false}
                                disabled={!isVisualFixture && (progressSaving || validCutoffMs === null || validCutoffMs <= 0 || validCutoffMs > (filmDetailVm?.runtimeMs || 0))}
                                onClick={() => {
                                  if (isVisualFixture) { handleToggleSpoiler(card.id); return; }
                                  if (validCutoffMs === null || !filmDetailVm?.editionId) return;
                                  setRevealError('');
                                  setRevealConfirmation({ cutoff: validCutoffMs, movieId: filmDetailVm.movieId, editionId: filmDetailVm.editionId });
                                }}
                                style={{
                                  width: 138,
                                  height: 38,
                                  padding: '8px 20px',
                                  background: '#E6E6EA',
                                  border: 'none',
                                  borderRadius: 20,
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  cursor: 'pointer',
                                  color: '#6B6B75',
                                  fontSize: 14,
                                  fontFamily: 'Pretendard, -apple-system, sans-serif',
                                  fontWeight: 500,
                                  lineHeight: '22px',
                                  boxSizing: 'border-box',
                                }}
                              >
                                Reveal Content
                              </button>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>}
          </section>

          {deletingReview && <DeleteConfirmation kind="review" onCancel={() => setDeletingReview(null)} onDelete={() => handleDeleteReview(deletingReview)} />}
          <AppModal isOpen={Boolean(revealConfirmation)} title="Reveal spoiler content?" size="sm"
            onClose={() => { if (!revealSaving) setRevealConfirmation(null); }}>
            <p>This updates your viewing position to at least {revealConfirmation ? new Date(revealConfirmation.cutoff).toISOString().slice(11, 19) : ''}.
              Story details and evidence up to that point may become visible. You can lock them again by moving the timeline back.</p>
            {revealError && <p role="alert">{revealError}</p>}
            <div className="reveal-confirm-actions">
              <button type="button" disabled={revealSaving} onClick={() => setRevealConfirmation(null)}>Cancel</button>
              <button type="button" disabled={revealSaving} onClick={confirmReveal}>{revealSaving ? 'Saving…' : 'Reveal Content'}</button>
            </div>
          </AppModal>

          {/* Section: Audience Reviews (Public Community Reviews) */}
          {!isVisualFixtureMode() && movieId && <ExternalCriticism movieId={movieId} />}
          <section
            data-testid="film-detail-audience-reviews"
            style={{
              width: 1920,
              boxSizing: 'border-box',
              background: '#FFFFFF',
              padding: '50px 120px',
              borderTop: '1px solid #F2F2F5',
              display: 'flex',
              flexDirection: 'column',
              gap: 24,
            }}
          >
            {/* Header & Controls */}
            <div className="audience-reviews-toolbar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: 1680 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <h2 style={{ fontSize: 20, fontFamily: 'Pretendard', fontWeight: 600, color: '#4A4A53', margin: 0 }}>
                  Audience Reviews ({publicReviews.length})
                </h2>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    type="button"
                    onClick={() => handleSortChange('popular')}
                    style={{
                      padding: '6px 14px',
                      borderRadius: 16,
                      border: 'none',
                      fontSize: 13,
                      fontFamily: 'Pretendard',
                      fontWeight: 600,
                      cursor: 'pointer',
                      background: reviewSort === 'popular' ? 'var(--Purple-500, #4C22F4)' : '#F2F2F5',
                      color: reviewSort === 'popular' ? '#FFFFFF' : '#6B6B75',
                    }}
                  >
                    Most Liked
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSortChange('recent')}
                    style={{
                      padding: '6px 14px',
                      borderRadius: 16,
                      border: 'none',
                      fontSize: 13,
                      fontFamily: 'Pretendard',
                      fontWeight: 600,
                      cursor: 'pointer',
                      background: reviewSort === 'recent' ? 'var(--Purple-500, #4C22F4)' : '#F2F2F5',
                      color: reviewSort === 'recent' ? '#FFFFFF' : '#6B6B75',
                    }}
                  >
                    Most Recent
                  </button>
                </div>
              </div>

              <button
                type="button"
                onClick={openNewReview}
                disabled={(authLoading || (isAuthenticated && reviewsLoading)) && !isVisualFixtureMode()}
                style={{
                  padding: '10px 20px',
                  background: 'var(--Purple-500, #4C22F4)',
                  borderRadius: 12,
                  border: 'none',
                  color: '#FFFFFF',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontFamily: 'Pretendard',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                {ownReview ? 'Edit My Review' : 'Write a Review'}
              </button>
            </div>

            {/* Content States */}
            {reviewsLoading ? (
              <LoadingState message="Loading audience reviews..." />
            ) : reviewsError ? (
              <ErrorState title="Failed to Load Reviews" message={reviewsError} onRetry={() => loadPublicReviews(movieId || 'the-bat-whispers-1930', reviewSort)} />
            ) : publicReviews.length === 0 ? (
              <EmptyState title="No Audience Reviews Yet" message="Be the first to share your interpretation or feedback on this film!" />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20, width: 1680 }}>
                {publicReviews.map((post) => {
                  const pId = post.post_id || post.id;
                  const isMasked = post.visibility === 'MASKED' || post.is_spoiler_masked || post.is_locked;
                  const isCommentsOpen = expandedCommentsPostId === pId;
                  const commentCount = post.comments_count ?? post.comment_count ?? 0;

                  return (
                    <div
                      key={pId}
                      id={`review-${pId}`}
                      data-testid={`audience-review-card-${pId}`}
                      style={{
                        padding: 24,
                        background: '#F8F8FA',
                        borderRadius: 16,
                        border: '1px solid #E6E6EA',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 14,
                      }}
                    >
                      {/* Metadata and existing owner/share actions. Review titles are not shown. */}
                      <div className="audience-review-heading" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <span style={{ fontSize: 14, fontWeight: 600, color: '#4A4A53', fontFamily: 'Pretendard' }}>
                            {post.author_name || 'Audience Member'}
                          </span>
                          <span style={{ fontSize: 12, color: '#6B6B75', fontFamily: 'Pretendard' }}>
                            {post.created_at ? new Date(post.created_at).toLocaleDateString() : ''}
                          </span>
                          {post.version_no && post.version_no > 1 && (
                            <span style={{ padding: '2px 8px', borderRadius: 4, background: '#E6E6EA', fontSize: 11, color: '#6B6B75', fontWeight: 600 }}>
                              v{post.version_no}
                            </span>
                          )}
                        </div>

                        <div style={{ display: 'flex', gap: 8 }}>
                          {canEditContent(post) && <><button
                            type="button"
                            data-testid="review-edit-btn"
                            onClick={() => handleStartEditReview(post)}
                            style={{
                              padding: '4px 10px',
                              background: '#E6E6EA',
                              border: 'none',
                              borderRadius: 6,
                              fontSize: 12,
                              fontWeight: 500,
                              cursor: 'pointer',
                              color: '#4A4A53',
                            }}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            data-testid="review-delete-btn"
                            onClick={() => setDeletingReview(pId)}
                            style={{
                              padding: '4px 10px',
                              background: '#FEE2E2',
                              border: 'none',
                              borderRadius: 6,
                              fontSize: 12,
                              fontWeight: 500,
                              cursor: 'pointer',
                              color: '#DC2626',
                            }}
                          >
                            Delete
                          </button></>}
                          <button
                            type="button"
                            data-testid="review-share-btn"
                            onClick={() => handleSharePost(pId)}
                            style={{
                              padding: '4px 10px',
                              background: '#F1F0FF',
                              border: 'none',
                              borderRadius: 6,
                              fontSize: 12,
                              fontWeight: 500,
                              cursor: 'pointer',
                              color: '#4C22F4',
                            }}
                          >
                            Share
                          </button>
                        </div>
                      </div>

                      <RatingStars rating={post.rating} />

                      {/* Body Content or Masked Warning */}
                      {isMasked ? (
                        <CommentSpoiler key={`${pId}:${post.version_no || 1}`} contentKind="review"
                          canReveal pending={revealingReviews.includes(pId)} inspectionStatus={post.inspection_status}
                          onReveal={() => void handleUnlockReview(pId, post.version_no || 1)} />
                      ) : (
                        <div data-testid="audience-review-body" style={{ fontSize: 15, color: '#2D2D34', fontFamily: 'Pretendard', lineHeight: '23px', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                          {post.body_markdown}
                        </div>
                      )}

                      {/* Bottom Bar: Likes & Comments Trigger */}
                      <div style={{ display: 'flex', gap: 16, alignItems: 'center', paddingTop: 6 }}>
                        <button
                          type="button"
                          aria-label={post.viewer_liked ? 'Unlike review' : 'Like review'}
                          aria-pressed={Boolean(post.viewer_liked)}
                          onClick={() => handleToggleReviewLike(pId, Boolean(post.viewer_liked))}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            border: 'none',
                            background: post.viewer_liked ? '#F1F0FF' : 'transparent',
                            padding: '6px 10px',
                            borderRadius: 8,
                            cursor: 'pointer',
                          }}
                        >
                          <svg width="18" height="18" viewBox="0 0 20 20" fill={post.viewer_liked ? '#4C22F4' : 'none'} stroke={post.viewer_liked ? '#4C22F4' : '#AFAFB8'} strokeWidth="1.5">
                            <path d="M10.293 17.4268C10.1097 17.5241 9.89032 17.5241 9.70703 17.4268L10 16.875L10.293 17.4268ZM16.875 6.875C16.875 5.17291 15.4302 3.75 13.5938 3.75C12.2253 3.75 11.0661 4.54535 10.5713 5.65674C10.4709 5.88228 10.2469 6.02783 10 6.02783C9.75312 6.02783 9.52909 5.88228 9.42871 5.65674C8.93392 4.54535 7.77467 3.75 6.40625 3.75C4.56977 3.75 3.125 5.17291 3.125 6.875C3.125 9.62122 4.84375 11.9659 6.67643 13.6743C7.58245 14.5189 8.49097 15.184 9.17399 15.638C9.5147 15.8645 9.79788 16.0376 9.9943 16.1532C9.99607 16.1542 9.99825 16.1554 10 16.1564C10.0017 16.1554 10.0039 16.1542 10.0057 16.1532C10.2021 16.0376 10.4853 15.8645 10.826 15.638C11.509 15.184 12.4175 14.5189 13.3236 13.6743C15.1562 11.9659 16.875 9.62122 16.875 6.875ZM18.125 6.875C18.125 10.1457 16.0937 12.8009 14.1764 14.5882C13.2076 15.4914 12.2409 16.1981 11.5177 16.6789C11.1556 16.9196 10.8526 17.1049 10.6388 17.2306C10.5322 17.2934 10.4478 17.3419 10.389 17.3747C10.3596 17.3911 10.3359 17.4034 10.3198 17.4121C10.3119 17.4164 10.3056 17.4203 10.3011 17.4227C10.299 17.4238 10.2975 17.4252 10.2962 17.4259L10.2938 17.4268L10 16.875L9.70622 17.4268L9.70378 17.4259C9.70246 17.4252 9.70101 17.4238 9.69889 17.4227C9.6944 17.4203 9.68815 17.4164 9.68018 17.4121C9.6641 17.4034 9.64045 17.3911 9.611 17.3747C9.55217 17.3419 9.46783 17.2934 9.36117 17.2306C9.14745 17.1049 8.84445 16.9196 8.48226 16.6789C7.75909 16.1981 6.7924 15.4914 5.82357 14.5882C3.90634 12.8009 1.875 10.1457 1.875 6.875C1.875 4.43495 3.928 2.5 6.40625 2.5C7.86485 2.5 9.16869 3.16863 10 4.21387C10.8313 3.16863 12.1352 2.5 13.5938 2.5C16.072 2.5 18.125 4.43495 18.125 6.875Z" />
                          </svg>
                          <span style={{ fontSize: 13, fontWeight: 600, color: post.viewer_liked ? '#4C22F4' : '#6B6B75' }}>
                            {post.like_count || 0}
                          </span>
                        </button>

                        <button
                          type="button"
                          data-testid="review-comments-toggle-btn"
                          onClick={() => handleToggleComments(pId)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            border: 'none',
                            background: isCommentsOpen ? '#F1F0FF' : 'transparent',
                            padding: '6px 10px',
                            borderRadius: 8,
                            cursor: 'pointer',
                          }}
                        >
                          <span style={{ fontSize: 14 }}>💬</span>
                          <span style={{ fontSize: 13, fontWeight: 600, color: isCommentsOpen ? '#4C22F4' : '#6B6B75' }}>
                            {`${commentCount} ${commentCount === 1 ? 'Comment' : 'Comments'}`}
                          </span>
                        </button>
                      </div>

                      {isCommentsOpen && <div data-testid="comments-thread"><ProofComments key={pId} proofId={`review:${pId}`} postId={pId} navigate={navigate} onCount={count => setPublicReviews(rows => rows.map(row => (row.post_id || row.id) === pId ? { ...row, comments_count: count } : row))} /></div>}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>

        {/* Reframe Moment Full Detail Modal */}
        {isVisualFixture && selectedReframeModalMoment && (
          <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', background: 'rgba(0,0,0,0.5)', zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 800, maxHeight: '85vh', background: 'white', borderRadius: 16, padding: '36px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--Purple-500, #4C22F4)', fontSize: 18, fontWeight: '700' }}>
                  {selectedReframeModalMoment.scene || 'SCENE 1'} {selectedReframeModalMoment.timestamp || '[00:04:12]'}
                </span>
                <button onClick={() => setSelectedReframeModalMoment(null)} style={{ background: 'none', border: 'none', fontSize: 24, cursor: 'pointer', color: '#AFAFB8' }}>✕</button>
              </div>
              <div style={{ fontSize: 24, fontWeight: '700', color: '#2D2D34' }}>
                {selectedReframeModalMoment.title}
              </div>
              <div style={{ color: '#4A4A53', fontSize: 16, lineHeight: '26px' }}>
                {selectedReframeModalMoment.interpretation}
              </div>
              <div style={{ padding: 16, background: '#F8F8FA', borderRadius: 12, borderLeft: '4px solid #4C22F4' }}>
                <div style={{ fontWeight: '600', marginBottom: 4 }}>Verified Timestamp Evidence</div>
                <div style={{ fontSize: 14, color: '#6B6B75' }}>Event ID: EVT_00412 | Frame: FRM_06048 | ClickHouse Narrative Causal Confidence: 99.4%</div>
              </div>
            </div>
          </div>
        )}

        {/* Review Write Modal (1:1 Figma Frame 5 / 84:12182) */}
        {showReviewModal && (
          <>
            <div data-layer="Rectangle 240655231" onClick={closeReview} style={{ width: '100vw', height: '100vh', left: 0, top: 0, position: 'fixed', background: 'rgba(0, 0, 0, 0.40)', zIndex: 1000 }} />
            <div role="dialog" aria-modal="true" aria-label="Write Review" data-testid="review-modal-content" data-layer="AppModal" data-node-id={reviewText.trim() ? "553:19617" : "553:19080"} style={{ width: 'min(795px, calc(100vw - 32px))', maxHeight: 'calc(100dvh - 32px)', overflowY: 'auto', paddingTop: 32, paddingBottom: 24, paddingLeft: 24, paddingRight: 24, left: '50%', top: '50%', transform: 'translate(-50%, -50%)', position: 'fixed', background: 'white', boxShadow: '0px 0px 20px rgba(30, 41, 59, 0.10)', borderRadius: 12, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'inline-flex', zIndex: 1001 }}>
              <div data-layer="Container" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'flex' }}>
                <div data-layer="Frame 1010106602" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'center', gap: 8, display: 'flex' }}>
                  <div data-layer="Container" style={{ alignSelf: 'stretch', justifyContent: 'center', alignItems: 'flex-start', gap: 16, display: 'inline-flex' }}>
                    <div data-layer="Container" style={{ flex: '1 1 0', justifyContent: 'center', alignItems: 'center', gap: 6, display: 'flex', flexWrap: 'wrap', alignContent: 'center' }}>
                      <div data-layer="Frame 1010106608" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 6, display: 'flex' }}>
                        <div data-layer="Title" style={{ textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 24, fontFamily: 'Pretendard', fontWeight: '600' }}>Write Review</div>
                      </div>
                    </div>
                    <button type="button" aria-label="Close review" disabled={isSubmittingReview} data-testid="review-modal-close" onClick={closeReview} data-layer="CustomButton" style={{ width: 24, height: 24, position: 'relative', background: 'rgba(255, 255, 255, 0)', borderRadius: 4, cursor: 'pointer' }}>
                      <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M6 17.999L18 5.99902M6 5.99902L18 17.999" stroke="var(--Semantic-Action-Foreground-Grayblue-Light-Default, #A0AEC0)" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  </div>
                  <div data-layer="Subtitle" style={{ alignSelf: 'stretch', textAlign: 'center', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500' }}>Leave a review for this film!</div>
                </div>
                <div data-layer="Slot" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 32, display: 'flex' }}>
                  <div data-layer="Frame 608228" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 32, display: 'flex' }}>
                    <div data-layer="Frame 2147227299" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'center', gap: 12, display: 'flex' }}>
                      <div data-layer="Frame 607541" style={{ alignSelf: 'stretch', justifyContent: 'center', alignItems: 'flex-start', gap: 12, display: 'inline-flex' }}>
                        <div data-layer="Frame 2147227208">
                          <svg width="210" height="42" viewBox="0 0 210 42" fill="none" xmlns="http://www.w3.org/2000/svg">
                            {[0, 42, 84, 126, 168].map((offset, starIdx) => (
                              <path
                                key={starIdx}
                                role="button"
                                tabIndex={0}
                                data-testid={`review-star-${starIdx + 1}`}
                                aria-label={`${starIdx + 1} stars`}
                                aria-pressed={reviewRating === starIdx + 1}
                                aria-disabled={isSubmittingReview}
                                onKeyDown={(e) => { if (!isSubmittingReview && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); setReviewRating(starIdx + 1); reviewRequestKey.current = crypto.randomUUID(); } }}
                                onClick={() => { if (!isSubmittingReview) { setReviewRating(starIdx + 1); reviewRequestKey.current = crypto.randomUUID(); } }}
                                d={`M${18.9823 + offset} 4.08822C${19.8077 + offset} 2.41592 ${22.1923 + offset} 2.41592 ${23.0177 + offset} 4.08822L${26.6482 + offset} 11.4446C${26.976 + offset} 12.1087 ${27.6095 + offset} 12.5689 ${28.3423 + offset} 12.6754L${36.4606 + offset} 13.8551C${38.3061 + offset} 14.1232 ${39.043 + offset} 16.3912 ${37.7076 + offset} 17.6929L${31.8331 + offset} 23.419C${31.3029 + offset} 23.9359 ${31.0609 + offset} 24.6807 ${31.1861 + offset} 25.4105L${32.5728 + offset} 33.496C${32.8881 + offset} 35.334 ${30.9588 + offset} 36.7357 ${29.3082 + offset} 35.8679L${22.047 + offset} 32.0504C${21.3915 + offset} 31.7058 ${20.6085 + offset} 31.7058 ${19.953 + offset} 32.0504L${12.6918 + offset} 35.8679C${11.0412 + offset} 36.7357 ${9.11194 + offset} 35.334 ${9.42719 + offset} 33.496L${10.8139 + offset} 25.4105C${10.9391 + offset} 24.6807 ${10.6971 + offset} 23.9359 ${10.1669 + offset} 23.419L${4.29245 + offset} 17.6929C${2.95704 + offset} 16.3912 ${3.69393 + offset} 14.1232 ${5.53943 + offset} 13.8551L${13.6577 + offset} 12.6754C${14.3905 + offset} 12.5689 ${15.024 + offset} 12.1087 ${15.3518 + offset} 11.4446L${18.9823 + offset} 4.08822Z`}
                                fill={starIdx < reviewRating ? '#FED200' : 'var(--Gray-100, #F2F2F5)'}
                                style={{ cursor: 'pointer' }}
                              />
                            ))}
                          </svg>
                        </div>
                      </div>
                    </div>
                    <div data-layer="profile-discover" style={{ alignSelf: 'stretch', height: 178, padding: 20, borderRadius: 12, outline: '1px var(--Gray-200, #E6E6EA) solid', outlineOffset: '-1px', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 16, display: 'flex' }}>
                      <textarea
                        data-testid="review-content-textarea"
                        aria-label="Your review"
                        maxLength={10000}
                        disabled={isSubmittingReview}
                        value={reviewText}
                        onChange={(e) => { setReviewText(e.target.value); reviewRequestKey.current = crypto.randomUUID(); }}
                        placeholder="Write your review here..."
                        style={{ width: '100%', height: '100%', border: 'none', outline: 'none', resize: 'none', background: 'transparent', color: reviewText ? 'var(--Gray-800, #2D2D34)' : 'var(--Gray-600, #6B6B75)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '500' }}
                      />
                    </div>
                  </div>
                  <label style={{display: 'flex', gap: 8, alignItems: 'center', fontSize: 14}}>
                    <input className="spoiler-checkbox" type="checkbox" checked={reviewContainsSpoilers} disabled={isSubmittingReview}
                      onChange={event => { setReviewContainsSpoilers(event.target.checked); reviewRequestKey.current = crypto.randomUUID(); }} />
                    Contains spoilers
                  </label>
                  <p style={{color: '#6B6B75', fontSize: 12, margin: 0}}>Your original text is preserved. Potential spoilers stay hidden until the reader chooses to reveal them.</p>
                  {reviewError && (
                    <div
                      data-testid="review-error-message"
                      role="alert"
                      style={{
                        alignSelf: 'stretch',
                        color: '#E53E3E',
                        fontSize: 13,
                        fontFamily: 'Pretendard',
                        fontWeight: '500',
                        padding: '10px 14px',
                        background: '#FFF5F5',
                        borderRadius: 8,
                        border: '1px solid #FEB2B2',
                        textAlign: 'center'
                      }}
                    >
                      {reviewError}
                    </div>
                  )}
                  <div data-layer="Frame 606878" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'inline-flex' }}>
                    <button type="button" disabled={isSubmittingReview} onClick={closeReview} data-layer="AppButton" style={{ flex: '1 1 0', paddingLeft: 20, paddingRight: 20, paddingTop: 16, paddingBottom: 16, background: 'var(--Gray-200, #E6E6EA)', borderRadius: 20, justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex', cursor: 'pointer' }}>
                      <div data-layer="Cancel" style={{ textAlign: 'center', color: 'var(--Gray-600, #6B6B75)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '500', lineHeight: '26px' }}>Cancel</div>
                    </button>
                    <button type="button" data-testid="review-submit-button" disabled={isSubmittingReview || !reviewText.trim() || reviewRating < 1} onClick={handleSaveReview} data-layer="AppButton" style={{ flex: '1 1 0', paddingLeft: 20, paddingRight: 20, paddingTop: 16, paddingBottom: 16, background: isSubmittingReview || !reviewText.trim() || reviewRating < 1 ? 'var(--Gray-400, #A0A0AA)' : 'var(--Purple-500, #4C22F4)', borderRadius: 20, justifyContent: 'center', alignItems: 'center', gap: 8, display: 'flex', cursor: isSubmittingReview ? 'not-allowed' : 'pointer' }}>
                      <div data-layer="SubmitReview" style={{ textAlign: 'center', color: 'white', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '500', lineHeight: '26px' }}>
                        {isSubmittingReview ? 'Posting…' : reviewError ? 'Try Again' : editingPost ? 'Save Changes' : 'Post Review'}
                      </div>
                    </button>
                  </div>
                </div>
              </div>
            </div>
            {/* Toast Notification (only shown on verified success) */}
            {showReviewToast && (
              <div data-layer="AppToast" style={{ height: 40, maxWidth: 500, padding: 12, left: 1634, top: 30, position: 'absolute', background: 'var(--Purple-50, #F1F0FF)', boxShadow: '0px 0px 12px rgba(30, 41, 59, 0.10)', borderRadius: 8, outline: '1px var(--Purple-500, #4C22F4) solid', outlineOffset: '-1px', justifyContent: 'flex-start', alignItems: 'center', gap: 16, display: 'inline-flex', zIndex: 1002 }}>
                <div data-layer="Frame 607914" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 8, display: 'flex' }}>
                  <div data-layer="Icon" style={{ width: 20, height: 20, position: 'relative' }}>
                    <svg width="100%" height="100%" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path fillRule="evenodd" clipRule="evenodd" d="M10 18C14.4183 18 18 14.4183 18 10C18 5.58172 14.4183 2 10 2C5.58172 2 2 5.58172 2 10C2 14.4183 5.58172 18 10 18ZM13.8566 8.19113C14.1002 7.85614 14.0261 7.38708 13.6911 7.14345C13.3561 6.89982 12.8871 6.97388 12.6434 7.30887L9.15969 12.099L7.28033 10.2197C6.98744 9.92678 6.51256 9.92678 6.21967 10.2197C5.92678 10.5126 5.92678 10.9874 6.21967 11.2803L8.71967 13.7803C8.87477 13.9354 9.08999 14.0149 9.30867 13.9977C9.52734 13.9805 9.72754 13.8685 9.85655 13.6911L13.8566 8.19113Z" fill="var(--Purple-400, #8277FF)" />
                    </svg>
                  </div>
                  <div data-layer="Description" style={{ color: 'var(--Gray-700, #4A4A53)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '500' }}>Review submitted successfully</div>
                </div>
                <div onClick={() => setShowReviewToast(false)} data-layer="CustomButton" style={{ width: 18, height: 18, position: 'relative', background: 'rgba(255, 255, 255, 0)', borderRadius: 4, cursor: 'pointer' }}>
                  <svg width="100%" height="100%" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M4.5 13.5L13.5 4.5M4.5 4.5L13.5 13.5" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
              </div>
            )}
          </>
        )}
        {/* Share Toast Notification */}
        {shareToast && (
          <div data-testid="share-toast-notification" style={{ position: 'fixed', bottom: 24, right: 24, background: '#1E293B', color: '#FFFFFF', padding: '12px 20px', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.15)', zIndex: 9999, fontSize: 14, fontFamily: 'Pretendard' }}>
            {shareToast}
          </div>
        )}
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // 2. CATALOG HUB VIEW (1:1 Figma Frame 73:7082)
  // --------------------------------------------------------------------------
  const categories = ['All', 'Thriller', 'Mystery', 'Horror', 'Sci-Fi', 'Action', 'Romance', 'Drama', 'Classic', 'Documentary'];

  const isFixture = isVisualFixtureMode();

  return (
    <div className="film-catalog-page" data-layer="Films" style={{ width: '100%', background: 'var(--Gray-0, white)', flexDirection: 'column', display: 'flex' }}>
      {/* Core Demo Notice Banner for Catalog */}
      <div
        data-testid="core-demo-notice-banner"
        style={{
          paddingTop: 24,
          paddingLeft: 120,
          paddingRight: 120,
        }}
      >
        <div
          style={{
            padding: '12px 20px',
            background: 'var(--Purple-50, #F1F0FF)',
            border: '1px solid var(--Purple-200, #B7B3FF)',
            borderRadius: 12,
            color: 'var(--Purple-700, #3412B3)',
            fontSize: 14,
            fontFamily: 'Pretendard, -apple-system, sans-serif',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span>ℹ️</span>
          <DemoFilmNotice films={films} navigate={navigate} />
        </div>
      </div>

      {!isFixture && <BoxOfficeChart navigate={navigate} />}
      {!isFixture && <FilmPicks films={films} navigate={navigate} />}
      {/* Box Office Ranking Section */}
      {isFixture && <div data-layer="Frame 2147227194" style={{ width: '100%', paddingTop: 30, paddingBottom: 70, paddingLeft: 120, paddingRight: 120, flexDirection: 'column', gap: 10, display: 'flex' }}>
        <div style={{ width: '100%', flexDirection: 'column', gap: 24, display: 'flex' }}>
          <div className="catalog-section-title" data-testid="browse-films-title" style={{ color: 'var(--Gray-800, #2D2D34)', fontSize: 28, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '39.20px' }}>
            {isFixture ? 'Box Office Ranking' : "RE:SCENE's PICK"}
          </div>
          <div style={{ width: '100%', overflow: 'hidden', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'inline-flex' }}>
            {boxOfficePage === 1 && (
              <div
                role="button"
                tabIndex={0}
                aria-label="Previous box office rankings (1-5)"
                data-testid="box-office-prev-btn"
                className="catalog-rank-arrow"
                onClick={() => setBoxOfficePage(0)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setBoxOfficePage(0); }}
                style={{ width: 60, height: 437, background: 'var(--Gray-100, #F2F2F5)', borderRadius: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
              >
                <svg width="100%" height="100%" viewBox="0 0 60 437" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect width="60" height="437" rx="16" transform="matrix(-1 0 0 1 60 0)" fill="var(--Gray-100, #F2F2F5)" />
                  <path d="M34 226.5L26 218.5L34 210.5" stroke="var(--Gray-700, #4A4A53)" strokeWidth="2.66667" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            )}
            <div style={{ flex: '1 1 0', overflow: 'hidden', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'flex' }}>
              {(isFixture
                ? (boxOfficePage === 0 ? [1, 2, 3, 4, 5] : [6, 7, 8, 9, 10]).map((rank, idx) => ({
                    rank,
                    movieId: 'the-bat-whispers-1930',
                    title: rank === 1 ? 'The Bat Whispers' : rank === 2 ? 'Inception' : rank === 3 ? 'Memories of Murder' : rank === 4 ? 'The Wailing' : rank === 5 ? 'Decision to Leave' : `Classic Pick ${rank}`,
                    posterPath: `/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-${idx === 0 ? 'I73-7086-73-6268' : idx === 1 ? 'I73-7087-73-6268' : idx === 2 ? 'I73-7088-73-6268' : idx === 3 ? 'I73-7089-73-6268' : 'I73-7090-73-6268'}.png`,
                    year: '1930',
                    destination: '/films/the-bat-whispers-1930',
                  }))
                : (boxOfficePage === 0
                    ? films.slice(0, 5).map((f, idx) => ({
                        rank: idx + 1,
                        movieId: f.movieId,
                        title: f.title,
                        posterPath: f.posterPath || `/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-${idx === 0 ? 'I73-7086-73-6268' : idx === 1 ? 'I73-7087-73-6268' : idx === 2 ? 'I73-7088-73-6268' : idx === 3 ? 'I73-7089-73-6268' : 'I73-7090-73-6268'}.png`,
                        year: f.year ? String(f.year) : '1930',
                        destination: f.destination || `/films/${f.movieId}`,
                      }))
                    : films.slice(5, 10).map((f, idx) => ({
                        rank: idx + 6,
                        movieId: f.movieId,
                        title: f.title,
                        posterPath: f.posterPath || `/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-${idx === 0 ? 'I73-7086-73-6268' : idx === 1 ? 'I73-7087-73-6268' : idx === 2 ? 'I73-7088-73-6268' : idx === 3 ? 'I73-7089-73-6268' : 'I73-7090-73-6268'}.png`,
                        year: f.year ? String(f.year) : '1930',
                        destination: f.destination || `/films/${f.movieId}`,
                      }))
                  )
              ).map((filmItem) => (
                <RankedFilmCard key={filmItem.rank} title={filmItem.title} rank={filmItem.rank}
                  posterPath={filmItem.posterPath} badge="RE:SCENE Pick" testId={`film-card-${filmItem.movieId}`}
                  fallbackPoster="/assets/poster_the_bat_whispers-Dg94dkRz.jpg"
                  onClick={() => navigate(filmItem.destination)}
                  metadata={<>{isFixture && <div>🍅 50%</div>}<div>{filmItem.year}</div><div>Featured</div></>} />
              ))}
            </div>
            {boxOfficePage === 0 && (isFixture || films.length > 5) && (
              <div
                role="button"
                tabIndex={0}
                aria-label="Next box office rankings (6-10)"
                data-testid="box-office-next-btn"
                className="catalog-rank-arrow"
                onClick={() => setBoxOfficePage(1)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setBoxOfficePage(1); }}
                style={{ width: 60, height: 437, background: 'var(--Gray-100, #F2F2F5)', borderRadius: 16, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
              >
                <svg width="100%" height="100%" viewBox="0 0 60 437" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect width="60" height="437" rx="16" fill="var(--Gray-100, #F2F2F5)" />
                  <path d="M26 226.5L34 218.5L26 210.5" stroke="var(--Gray-700, #4A4A53)" strokeWidth="2.66667" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            )}
          </div>
        </div>
      </div>

      }
      {!isFixture && (
        <div style={{ padding: '0 120px', display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <SortOptions label="Sort movies" value={catalogSort} onChange={setCatalogSort} options={movieSortOptions} />
        </div>
      )}
      {/* Category Section Rows */}
      {(isFixture ? ['Thriller & Mystery', 'Greatest Plot Twists', 'Classic Cinema Masterpieces', 'Hidden Clues & Detective Works'] : ['All Films']).map((catName, catIdx) => {
        const catFilms = (!isFixture && films.length > 0)
          ? [...films]
              .sort((a, b) => {
                return compareRanking(a, b, catalogSort) || a.movieId.localeCompare(b.movieId, 'en');
              })
          : null;
        return (
          <div key={catIdx} style={{ width: '100%', paddingLeft: 120, paddingRight: 120, paddingTop: 40, paddingBottom: 50, borderTop: '1px solid #F2F2F5', display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ color: 'var(--Gray-800, #2D2D34)', fontSize: 24, fontFamily: 'Pretendard', fontWeight: '600' }}>{catName}</div>
            </div>

            <div className="catalog-film-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 24 }}>
              {(isFixture ? [0, 1, 2, 3] : (catFilms || []).map((_, index) => index).slice((catalogPage - 1) * 12, catalogPage * 12)).map((itemIdx) => {
                const item = catFilms && catFilms[itemIdx] ? catFilms[itemIdx] : null;
                const destination = item ? item.destination : '/films/the-bat-whispers-1930';
                const title = item ? item.title : (itemIdx === 0 ? 'The Bat Whispers (1930)' : itemIdx === 1 ? 'Les Diaboliques (1955)' : itemIdx === 2 ? 'Double Indemnity (1944)' : 'Gaslight (1944)');
                const poster = item?.posterPath || `/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I73-786${itemIdx + 2}-73-6941.png`;

                return (
                  <div
                    key={itemIdx}
                    role="button"
                    tabIndex={0}
                    aria-label={title}
                    onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); navigate(destination); } }}
                    onClick={() => navigate(destination)}
                    style={{ display: 'flex', flexDirection: 'column', gap: 16, cursor: 'pointer' }}
                  >
                    <div style={{ width: '100%', height: 499, borderRadius: 12, overflow: 'hidden', background: '#D9D9D9' }}>
                      <img
                        src={poster}
                        alt={title}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        onError={(e) => {
                          e.currentTarget.style.visibility = 'hidden';
                        }}
                      />
                    </div>
                    <div style={{ textAlign: 'center', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {title}
                    </div>
                  </div>
                );
              })}
            </div>
            {!isFixture && <Pagination page={catalogPage} total={catFilms?.length || 0} onChange={setCatalogPage} />}
          </div>
        );
      })}

      {/* Category More Modal (1:1 Figma Frame 73:7855) */}
      {showFilmsMoreModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', background: 'rgba(0,0,0,0.5)', zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ width: 'min(1200px, calc(100vw - 32px))', maxHeight: 'calc(100dvh - 32px)', background: 'white', borderRadius: 16, padding: '40px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 32 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: '700', color: '#2D2D34' }}>Browse by Category</div>
              <button onClick={() => setShowFilmsMoreModal(false)} style={{ background: 'none', border: 'none', fontSize: 28, cursor: 'pointer', color: '#AFAFB8' }}>✕</button>
            </div>

            {/* Category Chips (10-grid) */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(10, 1fr)', gap: 12 }}>
              {categories.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(cat)}
                  style={{
                    padding: '10px 14px',
                    borderRadius: 20,
                    border: 'none',
                    background: selectedCategory === cat ? 'var(--Gray-700, #4A4A53)' : 'var(--Gray-100, #F2F2F5)',
                    color: selectedCategory === cat ? 'white' : 'var(--Gray-700, #4A4A53)',
                    fontSize: 16,
                    fontFamily: 'Pretendard',
                    fontWeight: '500',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap'
                  }}
                >
                  {cat}
                </button>
              ))}
            </div>

            {/* Movies Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 24 }}>
              {[0, 1, 2, 3, 4, 5, 6, 7].map((mIdx) => (
                <div
                  key={mIdx}
                  onClick={() => { setShowFilmsMoreModal(false); navigate('/films/the-bat-whispers-1930'); }}
                  style={{ display: 'flex', flexDirection: 'column', gap: 16, cursor: 'pointer' }}
                >
                  <div style={{ width: '100%', height: 400, borderRadius: 12, overflow: 'hidden', background: '#D9D9D9' }}>
                    <img
                      src="/assets/poster_the_bat_whispers-Dg94dkRz.jpg"
                      alt="Movie"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    />
                  </div>
                  <div style={{ textAlign: 'center', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600' }}>
                    {mIdx === 0 ? 'The Bat Whispers (1930)' : `Featured Film ${mIdx + 1}`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
