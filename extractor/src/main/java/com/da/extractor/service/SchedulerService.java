package com.da.extractor.service;

import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ScheduledFuture;

@Service
public class SchedulerService {

    private final TaskScheduler taskScheduler;


    private Map<String, ScheduledFuture<?>> scheduledTasks = new HashMap<>();

    public SchedulerService(TaskScheduler taskScheduler) {
        this.taskScheduler = taskScheduler;
    }

    public void createTask(String text, long rateMillis) {
        Runnable task = () -> System.out.println("Scheduled Task: " + text);

        ScheduledFuture<?> scheduledFuture = taskScheduler.scheduleAtFixedRate(
                task, Duration.ofMillis(rateMillis)
        );

        scheduledTasks.put(UUID.randomUUID().toString(), scheduledFuture);
    }
}
