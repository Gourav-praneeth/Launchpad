"""Deterministic job matching based only on explicit preferences and listing data."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from launchpad_worker.models import JobListing

DEFAULT_TARGET_TITLES = (
    "software engineer",
    "software developer",
    "backend engineer",
    "frontend engineer",
    "full stack engineer",
    "fullstack engineer",
    "mobile engineer",
    "platform engineer",
)

NEW_GRAD_MARKERS = (
    "new grad",
    "new graduate",
    "university graduate",
    "college graduate",
    "graduate software",
    "campus graduate",
)
ENTRY_LEVEL_MARKERS = (
    "entry level",
    "junior",
    "jr",
    "associate",
    "software engineer i",
    "software engineer 1",
    "developer i",
    "developer 1",
)
EARLY_CAREER_MARKERS = ("early career", "early careers", "emerging talent")
SENIOR_TITLE_MARKERS = (
    "senior",
    "sr",
    "staff",
    "principal",
    "lead",
    "manager",
    "director",
    "architect",
    "head",
    "vice president",
    "vp",
)

SPONSORSHIP_UNAVAILABLE_PATTERNS = (
    re.compile(r"\b(?:no|without)\s+(?:visa\s+)?sponsorship\b"),
    re.compile(r"\b(?:will not|cannot|unable to)\s+sponsor\b"),
    re.compile(r"\bnot (?:eligible|available) for sponsorship\b"),
    re.compile(r"\bwithout (?:current or future )?(?:visa )?sponsorship\b"),
)
SPONSORSHIP_AVAILABLE_PATTERNS = (
    re.compile(r"\b(?:visa )?sponsorship (?:is )?available\b"),
    re.compile(r"\bwe (?:can|do|will) sponsor\b"),
)


class MatchStatus(StrEnum):
    MATCHED = "matched"
    REVIEW = "review"
    REJECTED = "rejected"


class CareerLevel(StrEnum):
    NEW_GRAD = "new_grad"
    ENTRY_LEVEL = "entry_level"
    EARLY_CAREER = "early_career"
    EXPERIENCED = "experienced"
    UNKNOWN = "unknown"


class SponsorshipStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class SponsorshipPreference(StrEnum):
    REQUIRED = "required"
    NOT_REQUIRED = "not_required"
    ANY = "any"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MatchReason:
    """A stable reason code with user-readable evidence."""

    code: str
    message: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JobPreferences:
    """Explicit preferences used by the deterministic matcher."""

    target_titles: tuple[str, ...] = ()
    career_levels: tuple[CareerLevel, ...] = (
        CareerLevel.NEW_GRAD,
        CareerLevel.ENTRY_LEVEL,
        CareerLevel.EARLY_CAREER,
    )
    employment_types: tuple[str, ...] = ("full-time",)
    locations: tuple[str, ...] = ()
    workplace_types: tuple[str, ...] = ()
    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    sponsorship_preference: SponsorshipPreference = SponsorshipPreference.ANY
    include_senior_roles: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "target_titles",
            "employment_types",
            "locations",
            "workplace_types",
            "include_keywords",
            "exclude_keywords",
        ):
            values = getattr(self, field_name)
            if any(not value.strip() for value in values):
                raise ValueError(f"{field_name} cannot contain blank values")
        if CareerLevel.UNKNOWN in self.career_levels:
            raise ValueError("unknown cannot be an eligible career level")


@dataclass(frozen=True, slots=True)
class MatchResult:
    """An explainable eligibility decision with no freshness-based score."""

    status: MatchStatus
    career_level: CareerLevel
    sponsorship_status: SponsorshipStatus
    match_reasons: tuple[MatchReason, ...]
    review_reasons: tuple[MatchReason, ...]
    rejection_reasons: tuple[MatchReason, ...]

    @property
    def is_match(self) -> bool:
        """Return whether the job fully satisfies the configured preferences."""
        return self.status is MatchStatus.MATCHED


class JobMatcher:
    """Apply transparent deterministic rules to one normalized job listing."""

    def evaluate(self, listing: JobListing, preferences: JobPreferences) -> MatchResult:
        match_reasons: list[MatchReason] = []
        review_reasons: list[MatchReason] = []
        rejection_reasons: list[MatchReason] = []

        normalized_title = normalize_match_text(listing.title)
        searchable_text = normalize_match_text(
            " ".join(
                value for value in (listing.title, listing.description, listing.location) if value
            )
        )

        self._evaluate_title(
            normalized_title,
            preferences,
            match_reasons,
            rejection_reasons,
        )
        career_level = classify_career_level(listing.title)
        self._evaluate_career_level(
            career_level,
            normalized_title,
            preferences,
            match_reasons,
            review_reasons,
            rejection_reasons,
        )
        self._evaluate_employment_type(
            listing.employment_type,
            preferences,
            match_reasons,
            review_reasons,
            rejection_reasons,
        )
        self._evaluate_workplace_type(
            listing.workplace_type,
            preferences,
            match_reasons,
            review_reasons,
            rejection_reasons,
        )
        self._evaluate_location(
            listing.location,
            preferences,
            match_reasons,
            review_reasons,
            rejection_reasons,
        )
        self._evaluate_keywords(
            searchable_text,
            preferences,
            match_reasons,
            rejection_reasons,
        )
        sponsorship_status = classify_sponsorship(listing.description)
        self._evaluate_sponsorship(
            sponsorship_status,
            preferences,
            match_reasons,
            review_reasons,
            rejection_reasons,
        )

        if rejection_reasons:
            status = MatchStatus.REJECTED
        elif review_reasons:
            status = MatchStatus.REVIEW
        else:
            status = MatchStatus.MATCHED
        return MatchResult(
            status=status,
            career_level=career_level,
            sponsorship_status=sponsorship_status,
            match_reasons=tuple(match_reasons),
            review_reasons=tuple(review_reasons),
            rejection_reasons=tuple(rejection_reasons),
        )

    @staticmethod
    def _evaluate_title(
        normalized_title: str,
        preferences: JobPreferences,
        matches: list[MatchReason],
        rejections: list[MatchReason],
    ) -> None:
        target_titles = preferences.target_titles or DEFAULT_TARGET_TITLES
        matched_titles = matching_terms(normalized_title, target_titles)
        if matched_titles:
            matches.append(
                MatchReason(
                    code="title_match",
                    message="Job title matches a target role.",
                    evidence=matched_titles,
                )
            )
        else:
            rejections.append(
                MatchReason(
                    code="title_not_targeted",
                    message="Job title does not match a target role.",
                )
            )

    @staticmethod
    def _evaluate_career_level(
        career_level: CareerLevel,
        normalized_title: str,
        preferences: JobPreferences,
        matches: list[MatchReason],
        reviews: list[MatchReason],
        rejections: list[MatchReason],
    ) -> None:
        senior_markers = matching_terms(normalized_title, SENIOR_TITLE_MARKERS)
        if senior_markers and not preferences.include_senior_roles:
            rejections.append(
                MatchReason(
                    code="senior_role_excluded",
                    message="Senior-level roles are excluded by default.",
                    evidence=senior_markers,
                )
            )
            return

        if career_level is CareerLevel.UNKNOWN:
            reviews.append(
                MatchReason(
                    code="career_level_unknown",
                    message="Career level is not explicit and needs review.",
                )
            )
        elif career_level in preferences.career_levels:
            matches.append(
                MatchReason(
                    code="career_level_match",
                    message="Career level matches your preferences.",
                    evidence=(career_level.value,),
                )
            )
        else:
            rejections.append(
                MatchReason(
                    code="career_level_mismatch",
                    message="Career level does not match your preferences.",
                    evidence=(career_level.value,),
                )
            )

    @staticmethod
    def _evaluate_employment_type(
        value: str | None,
        preferences: JobPreferences,
        matches: list[MatchReason],
        reviews: list[MatchReason],
        rejections: list[MatchReason],
    ) -> None:
        allowed = canonical_terms(preferences.employment_types, canonical_employment_type)
        if not allowed:
            return
        employment_type = canonical_employment_type(value)
        if employment_type is None:
            reviews.append(
                MatchReason(
                    code="employment_type_unknown",
                    message="Employment type is unavailable and needs review.",
                )
            )
        elif employment_type in allowed:
            matches.append(
                MatchReason(
                    code="employment_type_match",
                    message="Employment type matches your preferences.",
                    evidence=(employment_type,),
                )
            )
        else:
            rejections.append(
                MatchReason(
                    code="employment_type_mismatch",
                    message="Employment type does not match your preferences.",
                    evidence=(employment_type,),
                )
            )

    @staticmethod
    def _evaluate_workplace_type(
        value: str | None,
        preferences: JobPreferences,
        matches: list[MatchReason],
        reviews: list[MatchReason],
        rejections: list[MatchReason],
    ) -> None:
        allowed = canonical_terms(preferences.workplace_types, canonical_workplace_type)
        if not allowed:
            return
        workplace_type = canonical_workplace_type(value)
        if workplace_type is None:
            reviews.append(
                MatchReason(
                    code="workplace_type_unknown",
                    message="Work arrangement is unavailable and needs review.",
                )
            )
        elif workplace_type in allowed:
            matches.append(
                MatchReason(
                    code="workplace_type_match",
                    message="Work arrangement matches your preferences.",
                    evidence=(workplace_type,),
                )
            )
        else:
            rejections.append(
                MatchReason(
                    code="workplace_type_mismatch",
                    message="Work arrangement does not match your preferences.",
                    evidence=(workplace_type,),
                )
            )

    @staticmethod
    def _evaluate_location(
        value: str | None,
        preferences: JobPreferences,
        matches: list[MatchReason],
        reviews: list[MatchReason],
        rejections: list[MatchReason],
    ) -> None:
        if not preferences.locations:
            return
        if value is None or not value.strip():
            reviews.append(
                MatchReason(
                    code="location_unknown",
                    message="Location is unavailable and needs review.",
                )
            )
            return
        matched_locations = matching_terms(normalize_match_text(value), preferences.locations)
        if matched_locations:
            matches.append(
                MatchReason(
                    code="location_match",
                    message="Location matches your preferences.",
                    evidence=matched_locations,
                )
            )
        else:
            rejections.append(
                MatchReason(
                    code="location_mismatch",
                    message="Location does not match your preferences.",
                    evidence=(value.strip(),),
                )
            )

    @staticmethod
    def _evaluate_keywords(
        searchable_text: str,
        preferences: JobPreferences,
        matches: list[MatchReason],
        rejections: list[MatchReason],
    ) -> None:
        excluded = matching_terms(searchable_text, preferences.exclude_keywords)
        if excluded:
            rejections.append(
                MatchReason(
                    code="excluded_keyword",
                    message="Listing contains an excluded keyword.",
                    evidence=excluded,
                )
            )

        if preferences.include_keywords:
            included = matching_terms(searchable_text, preferences.include_keywords)
            if included:
                matches.append(
                    MatchReason(
                        code="included_keyword",
                        message="Listing contains a requested keyword.",
                        evidence=included,
                    )
                )
            else:
                rejections.append(
                    MatchReason(
                        code="required_keyword_missing",
                        message="Listing contains none of the requested keywords.",
                    )
                )

    @staticmethod
    def _evaluate_sponsorship(
        status: SponsorshipStatus,
        preferences: JobPreferences,
        matches: list[MatchReason],
        reviews: list[MatchReason],
        rejections: list[MatchReason],
    ) -> None:
        if preferences.sponsorship_preference is not SponsorshipPreference.REQUIRED:
            return
        if status is SponsorshipStatus.AVAILABLE:
            matches.append(
                MatchReason(
                    code="sponsorship_available",
                    message="Listing explicitly states sponsorship is available.",
                )
            )
        elif status is SponsorshipStatus.UNAVAILABLE:
            rejections.append(
                MatchReason(
                    code="sponsorship_unavailable",
                    message="Listing explicitly states sponsorship is unavailable.",
                )
            )
        else:
            reviews.append(
                MatchReason(
                    code="sponsorship_unknown",
                    message="Sponsorship information is unavailable and needs review.",
                )
            )


def normalize_match_text(value: str) -> str:
    """Normalize punctuation and whitespace for case-insensitive phrase matching."""
    normalized = re.sub(r"[^\w+#]+", " ", value.casefold(), flags=re.UNICODE)
    return " ".join(normalized.split())


def matching_terms(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    """Return configured terms found as whole normalized phrases, in stable order."""
    padded_text = f" {text} "
    matches: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = normalize_match_text(term)
        if normalized and normalized not in seen and f" {normalized} " in padded_text:
            matches.append(term.strip())
            seen.add(normalized)
    return tuple(matches)


def classify_career_level(title: str) -> CareerLevel:
    """Classify only explicit title evidence; never infer from freshness or a resume."""
    normalized = normalize_match_text(title)
    if matching_terms(normalized, NEW_GRAD_MARKERS):
        return CareerLevel.NEW_GRAD
    if matching_terms(normalized, ENTRY_LEVEL_MARKERS):
        return CareerLevel.ENTRY_LEVEL
    if matching_terms(normalized, EARLY_CAREER_MARKERS):
        return CareerLevel.EARLY_CAREER
    if matching_terms(normalized, SENIOR_TITLE_MARKERS):
        return CareerLevel.EXPERIENCED
    return CareerLevel.UNKNOWN


def classify_sponsorship(description: str | None) -> SponsorshipStatus:
    """Classify sponsorship only when the listing contains explicit evidence."""
    if not description:
        return SponsorshipStatus.UNKNOWN
    normalized = normalize_match_text(description)
    if any(pattern.search(normalized) for pattern in SPONSORSHIP_UNAVAILABLE_PATTERNS):
        return SponsorshipStatus.UNAVAILABLE
    if any(pattern.search(normalized) for pattern in SPONSORSHIP_AVAILABLE_PATTERNS):
        return SponsorshipStatus.AVAILABLE
    return SponsorshipStatus.UNKNOWN


def canonical_employment_type(value: str | None) -> str | None:
    """Map reliable employment metadata to stable preference values."""
    if value is None:
        return None
    normalized = normalize_match_text(value)
    mappings = {
        "full time": "full-time",
        "fulltime": "full-time",
        "permanent": "full-time",
        "part time": "part-time",
        "parttime": "part-time",
        "intern": "internship",
        "internship": "internship",
        "contract": "contract",
        "contractor": "contract",
        "temporary": "temporary",
    }
    return mappings.get(normalized)


def canonical_workplace_type(value: str | None) -> str | None:
    """Map reliable workplace metadata to remote, hybrid, or on-site."""
    if value is None:
        return None
    normalized = normalize_match_text(value)
    mappings = {
        "remote": "remote",
        "hybrid": "hybrid",
        "on site": "on-site",
        "onsite": "on-site",
        "in office": "on-site",
    }
    return mappings.get(normalized)


def canonical_terms(
    values: tuple[str, ...],
    canonicalizer: Callable[[str | None], str | None],
) -> tuple[str, ...]:
    """Canonicalize configured values without allowing duplicates."""
    normalized = (canonicalizer(value) for value in values)
    return tuple(dict.fromkeys(value for value in normalized if value is not None))
