package com.da.anomaliesinsightsmodule.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Rate limiter for email notifications to prevent spam.
 * Limits emails per recipient based on configurable thresholds.
 */
@Service
public class EmailRateLimiterService {

    private final Logger logger = LoggerFactory.getLogger(EmailRateLimiterService.class);

    // Map of email address -> list of send timestamps
    private final ConcurrentMap<String, CopyOnWriteArrayList<Instant>> emailSendHistory = new ConcurrentHashMap<>();

    @Value("${email.rate-limit.max-per-hour:10}")
    private int maxEmailsPerHour;

    @Value("${email.rate-limit.cooldown-minutes:5}")
    private int cooldownMinutes;

    /**
     * Check if an email can be sent to the given recipient.
     *
     * @param recipientEmail the email address to check
     * @return true if the email can be sent, false if rate limited
     */
    public boolean canSendEmail(String recipientEmail) {
        if (recipientEmail == null || recipientEmail.isBlank()) {
            return false;
        }

        String normalizedEmail = recipientEmail.toLowerCase().trim();
        Instant now = Instant.now();
        Instant oneHourAgo = now.minus(1, ChronoUnit.HOURS);
        Instant cooldownThreshold = now.minus(cooldownMinutes, ChronoUnit.MINUTES);

        CopyOnWriteArrayList<Instant> history = emailSendHistory.computeIfAbsent(
                normalizedEmail, k -> new CopyOnWriteArrayList<>()
        );

        // Clean up old entries (older than 1 hour)
        List<Instant> recentSends = history.stream()
                .filter(timestamp -> timestamp.isAfter(oneHourAgo))
                .collect(Collectors.toList());

        // Update history with cleaned list
        history.clear();
        history.addAll(recentSends);

        // Check cooldown (minimum time between emails to same recipient)
        if (!recentSends.isEmpty()) {
            Instant lastSend = recentSends.get(recentSends.size() - 1);
            if (lastSend.isAfter(cooldownThreshold)) {
                logger.info("Rate limit: Email to {} blocked by cooldown. Last sent: {}", 
                        normalizedEmail, lastSend);
                return false;
            }
        }

        // Check hourly limit
        if (recentSends.size() >= maxEmailsPerHour) {
            logger.info("Rate limit: Email to {} blocked. {} emails sent in last hour (max: {})", 
                    normalizedEmail, recentSends.size(), maxEmailsPerHour);
            return false;
        }

        return true;
    }

    /**
     * Record that an email was sent to the given recipient.
     * Call this after successfully sending an email.
     *
     * @param recipientEmail the email address that was sent to
     */
    public void recordEmailSent(String recipientEmail) {
        if (recipientEmail == null || recipientEmail.isBlank()) {
            return;
        }

        String normalizedEmail = recipientEmail.toLowerCase().trim();
        CopyOnWriteArrayList<Instant> history = emailSendHistory.computeIfAbsent(
                normalizedEmail, k -> new CopyOnWriteArrayList<>()
        );
        history.add(Instant.now());

        logger.debug("Recorded email sent to {}. Total in history: {}", normalizedEmail, history.size());
    }

    /**
     * Get the number of emails sent to a recipient in the last hour.
     *
     * @param recipientEmail the email address to check
     * @return the number of emails sent in the last hour
     */
    public int getEmailCountLastHour(String recipientEmail) {
        if (recipientEmail == null || recipientEmail.isBlank()) {
            return 0;
        }

        String normalizedEmail = recipientEmail.toLowerCase().trim();
        CopyOnWriteArrayList<Instant> history = emailSendHistory.get(normalizedEmail);

        if (history == null) {
            return 0;
        }

        Instant oneHourAgo = Instant.now().minus(1, ChronoUnit.HOURS);
        return (int) history.stream()
                .filter(timestamp -> timestamp.isAfter(oneHourAgo))
                .count();
    }

    /**
     * Get rate limit status message for a recipient.
     *
     * @param recipientEmail the email address to check
     * @return a status message describing the rate limit state
     */
    public String getRateLimitStatus(String recipientEmail) {
        int count = getEmailCountLastHour(recipientEmail);
        boolean canSend = canSendEmail(recipientEmail);

        return String.format("Email: %s, Sent last hour: %d/%d, Can send: %s",
                recipientEmail, count, maxEmailsPerHour, canSend);
    }
}
